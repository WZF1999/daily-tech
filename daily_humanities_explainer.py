#!/usr/bin/env python3
"""
每日人文科普(政治 · 经济 · 历史)—— GitHub Actions 版
流程: 按日期轮换选题 -> OpenAI 联网搜索并写科普 -> 通过 Gmail SMTP 发到自己收件箱

依赖: openai>=1.40
需要的环境变量(与科技版共用同一套 Secrets):
  OPENAI_API_KEY      OpenAI 的 API key
  GMAIL_USER          你的 Gmail 地址
  GMAIL_APP_PASSWORD  Gmail 的"应用专用密码"(16 位)
  MAIL_TO             收件人(可选, 默认= GMAIL_USER)
"""

import os
import sys
import json
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from openai import OpenAI

# ---------- 选题池(政治 · 经济 · 历史; 可自由增删) ----------
TOPICS = [
    "通货膨胀与恶性通胀的来龙去脉", "布雷顿森林体系的建立与瓦解", "马歇尔计划如何重塑战后欧洲",
    "凯恩斯主义与政府刺激经济", "三权分立思想的由来", "1929 年大萧条是怎么发生的",
    "罗马帝国为何衰亡", "石油美元体系如何运作", "欧元的诞生与难题",
    "冷战是如何开始的", "工业革命如何改变社会结构", "美国宪法是怎么制定出来的",
    "法国大革命的起因与影响", "社会契约论讲了什么", "亚当·斯密与'看不见的手'",
    "比较优势与自由贸易为何双赢", "中央银行制度是怎么来的", "金本位的兴衰",
    "民族国家是如何形成的", "黑死病如何重塑了欧洲", "丝绸之路与早期全球化",
    "鸦片战争背后的经济动因", "1970 年代的滞胀难题", "广场协议与日本经济",
    "2008 年次贷危机是怎么爆发的", "关税与贸易战的逻辑", "议会制与总统制的区别",
    "福利国家的兴起", "民主与共和到底差在哪", "文艺复兴的社会根源",
    "凡尔赛条约如何埋下二战的种子", "布尔什维克革命的来龙去脉", "殖民主义与全球贸易体系",
    "大宪章与现代法治的起点", "东亚经济奇迹是怎么实现的", "通货紧缩为什么也很可怕",
    "美苏太空竞赛背后的政治博弈", "现代央行的通胀目标制", "全球化的兴起与退潮",
    "选举制度: 多数制与比例代表制",
]


def pick_topic() -> str:
    # 按日期轮换: 每天取下一个话题, 跑完一整轮才回到开头, 一轮内绝不重复。
    day_index = datetime.date.today().toordinal()
    return TOPICS[day_index % len(TOPICS)]


INSTRUCTIONS = (
    "你是一名严肃的中文人文科普作者, 风格类似优质的财经/历史专栏(如《经济学人》中文、三联生活周刊深度报道)。"
    "话题范围是政治、经济、历史。请围绕给定话题, 先用联网搜索找 2-4 篇高质量、可信、面向大众的文章或权威资料"
    "(中英文皆可, 优先权威媒体、百科、学术普及读物), 再据此写作。\n\n"
    "【写作风格 · 必须遵守】\n"
    "1. 写成一篇有标题(<h1>)的完整文章, 用小标题(<h2>)分节, 关键术语可加粗(<strong>)。\n"
    "2. 语气专业、克制、是认真的书面表达; 不要口语化抖机灵, 不要轻飘飘的博客腔, 不要浮夸卖弄的比喻, "
    "也不要'一句话钩子''反直觉冷知识'这类模板小标题。\n"
    "3. 最重要的一条: 很多人文术语其实是把一大堆现实运动'打包'成了一个短语(例如'竞争性货币贬值''贸易壁垒')。"
    "每当出现这种术语, 必须当场用一个具体、日常的例子, 把这个短语背后到底在发生什么讲清楚(例如用一条街上店铺"
    "互相降价抢客解释竞争性贬值、用进口商品被加税导致变贵解释贸易壁垒、用小岛上钱变多而货物没变解释通胀)。"
    "绝不堆砌未经解释的专有名词。\n"
    "4. 涉及经济等话题时, 该用公式/简单关系式就用(如通胀率、供需、复利等), 但必须把每个符号用通俗语言解释清楚, "
    "并说明这个式子直观上意味着什么。\n"
    "5. 多用真实的历史事例和数字让叙述具体可感(例如 1923 年魏玛德国用独轮车推钞票买面包)。\n"
    "6. 既要专业准确, 又要生动易懂。涉及仍有争议的政治议题时, 保持客观, 呈现不同视角而非站队。\n\n"
    "【结构】\n"
    "正文(主题讲解, 约 500-900 字): 自然引入今天的话题, 循序渐进讲清它的来龙去脉与内在逻辑, "
    "中间穿插具体事例; 复杂的因果关系要拆开、用例子讲透, 不要一句话带过。\n"
    "随后另起一节 <h2>基础概念扫盲</h2>(约 300-600 字): 挑出正文里 2-3 个关键前置概念, "
    "每个用通俗语言加具体例子讲清是什么、为什么与本话题有关。\n"
    "最后一节 <h2>延伸阅读</h2>: 列出 2-4 篇你检索并核实过的真实文章, 给出标题 + 真实可点击链接(<a href>)。\n\n"
    "只输出一个 JSON 对象, 不要加 Markdown 代码块标记, 格式严格为:\n"
    '{"subject": "邮件主题(以【每日人文科普】开头)", "html_body": "完整的 HTML 正文"}\n'
    "html_body 用简单内联样式即可, 标题用 <h1>/<h2>, 段落用 <p>, 链接用 <a href>。"
)


def generate_email(topic: str) -> dict:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        instructions=INSTRUCTIONS,
        input=f"今天的话题: {topic}",
    )

    text = resp.output_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    try:
        data = json.loads(text)
        subject = data["subject"]
        html_body = data["html_body"]
    except Exception:
        subject = f"【每日人文科普】{topic}"
        html_body = f"<pre style='white-space:pre-wrap;font-family:sans-serif'>{text}</pre>"
    return {"subject": subject, "html_body": html_body}


def send_email(subject: str, html_body: str):
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to_addr = os.environ.get("MAIL_TO", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("每日人文科普", user))
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())


def main():
    topic = pick_topic()
    print(f"今天的话题: {topic}", flush=True)
    email = generate_email(topic)
    print(f"主题: {email['subject']}", flush=True)
    send_email(email["subject"], email["html_body"])
    print("已发送 ✅", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        sys.exit(1)
