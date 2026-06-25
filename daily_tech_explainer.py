#!/usr/bin/env python3
"""
每日科技科普 —— GitHub Actions 版
流程: 按日期轮换选题 -> OpenAI 联网搜索并写科普 -> 通过 Gmail SMTP 发到自己收件箱

依赖: openai>=1.40
需要的环境变量(在 GitHub 仓库 Settings -> Secrets and variables -> Actions 里配置):
  OPENAI_API_KEY      OpenAI 的 API key
  GMAIL_USER          你的 Gmail 地址, 如 zhifanwang2017@gmail.com
  GMAIL_APP_PASSWORD  Gmail 的"应用专用密码"(16 位, 见 README)
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

# ---------- 选题池(灵感来源, 可自由增删; 加得越多, 不重复的周期越长) ----------
TOPICS = [
    "二维码是怎么编码和纠错的", "Google 搜索的排序原理 (PageRank 及之后)",
    "无线电是怎么传输信息的", "无线充电的电磁感应原理", "主动降噪耳机如何抵消噪声",
    "GPS 如何用卫星给你定位", "电容触摸屏如何感知手指", "人脸识别背后的算法",
    "HTTPS 加密是怎么保证安全的", "JPEG 图片压缩的原理", "CDN 如何让网页加速",
    "蓝牙如何配对与传输", "SSD 固态硬盘如何存数据", "机械硬盘的读写原理",
    "激光是怎么产生的", "核磁共振 (MRI) 成像原理", "电梯的调度算法",
    "量子计算到底快在哪", "光刻机如何造出芯片", "Shazam 如何几秒听歌识曲",
    "推荐算法是怎么猜你喜欢的", "ABS 防抱死刹车的原理", "电容麦克风如何收声",
    "OLED 屏幕的发光原理", "指纹解锁如何识别你", "5G 比 4G 快在哪",
    "北斗 / GNSS 定位原理", "哈希函数与密码存储", "公钥密码 (RSA) 的数学直觉",
    "锂电池的充放电与 BMS", "热成像相机如何看见温度", "雷达如何测距测速",
    "声呐如何在水下探测", "涡轮增压如何提升马力", "降落伞的空气动力学",
    "Wi-Fi 如何在空中分配信道", "USB-C 与快充协议", "光纤如何用光传数据",
    "区块链如何防篡改", "数字水印如何隐藏信息",
]


def pick_topic() -> str:
    # 按日期轮换: 每天取下一个话题, 跑完一整轮才回到开头。
    # 这样在一轮(len(TOPICS) 天)之内绝不重复, 且无需保存任何状态。
    day_index = datetime.date.today().toordinal()
    return TOPICS[day_index % len(TOPICS)]


INSTRUCTIONS = (
    "你是一名严肃的中文科普作者, 风格类似优质科学/科技专栏(如《环球科学》《科学美国人》中文版)。"
    "请围绕给定话题, 先用联网搜索找 2-4 篇高质量、可信、面向大众的科普文章或权威资料(中英文皆可), 再据此写作。\n\n"
    "【写作风格 · 必须遵守】\n"
    "1. 写成一篇有标题(<h1>)的完整文章, 用小标题(<h2>)分节, 关键术语可加粗(<strong>)。\n"
    "2. 语气专业、克制、是认真的书面表达; 不要口语化抖机灵, 不要轻飘飘的博客腔, 不要浮夸卖弄的比喻, "
    "也不要'一句话钩子''反直觉冷知识'这类模板小标题。\n"
    "3. 最重要的一条: 每当出现一个普通读者可能不懂的术语, 或一个被'打包'成短语的复杂机制, 必须当场用一个"
    "具体、日常的例子把里面究竟在发生什么讲清楚(例如用秋千两侧一推一挡解释反相抵消、用水面波纹解释波)。"
    "绝不堆砌未经解释的专有名词。\n"
    "4. 解释原理该用公式时就用公式(尤其物理/工程类话题), 但必须把公式里每个符号用通俗语言解释清楚, "
    "并说明这个式子直观上意味着什么; 公式用普通文本或简单 HTML 表示即可。\n"
    "5. 既要专业准确, 又要生动易懂。\n\n"
    "【结构】\n"
    "正文(主题讲解, 约 400-800 字): 用一两句自然引入今天的话题, 然后循序渐进讲清它的原理/运作方式, "
    "中间按需穿插例子和公式。\n"
    "随后另起一节 <h2>基础概念扫盲</h2>(约 300-600 字): 挑出正文里 2-3 个关键前置概念(例如讲雷达时的"
    "电磁波、多普勒效应), 每个用通俗语言加具体例子讲清是什么、为什么与本话题有关, 需要公式时一并给出并解释每个符号。\n"
    "最后一节 <h2>延伸阅读</h2>: 列出 2-4 篇你检索并核实过的真实文章, 给出标题 + 真实可点击链接(<a href>)。\n\n"
    "只输出一个 JSON 对象, 不要加 Markdown 代码块标记, 格式严格为:\n"
    '{"subject": "邮件主题(以【每日科技科普】开头)", "html_body": "完整的 HTML 正文"}\n'
    "html_body 用简单内联样式即可, 标题用 <h1>/<h2>, 段落用 <p>, 链接用 <a href>。"
)


def generate_email(topic: str) -> dict:
    """调用 OpenAI(带联网搜索)生成 {subject, html_body}"""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        instructions=INSTRUCTIONS,
        input=f"今天的话题: {topic}",
    )

    text = resp.output_text.strip()
    # 容错: 去掉可能的 ```json 包裹
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    try:
        data = json.loads(text)
        subject = data["subject"]
        html_body = data["html_body"]
    except Exception:
        # 解析失败也别让任务白跑, 直接把全文当正文发出去
        subject = f"【每日科技科普】{topic}"
        html_body = f"<pre style='white-space:pre-wrap;font-family:sans-serif'>{text}</pre>"
    return {"subject": subject, "html_body": html_body}


def send_email(subject: str, html_body: str):
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to_addr = os.environ.get("MAIL_TO", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("每日科技科普", user))
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
