#!/usr/bin/env python3
"""
每日科技科普 —— GitHub Actions 版
流程: 随机选题 -> OpenAI 联网搜索并写科普 -> 通过 Gmail SMTP 发到自己收件箱

依赖: openai>=1.40
需要的环境变量(在 GitHub 仓库 Settings -> Secrets and variables -> Actions 里配置):
  OPENAI_API_KEY   OpenAI 的 API key
  GMAIL_USER       你的 Gmail 地址, 如 zhifanwang2017@gmail.com
  GMAIL_APP_PASSWORD  Gmail 的"应用专用密码"(16 位, 见 README)
  MAIL_TO          收件人(可选, 默认= GMAIL_USER)
"""

import os
import sys
import json
import random
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from openai import OpenAI

# ---------- 选题池(灵感来源, 可自由增删) ----------
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
    "条形码与二维码的区别", "Wi-Fi 如何在空中分配信道", "USB-C 与快充协议",
    "光纤如何用光传数据", "区块链如何防篡改", "数字水印如何隐藏信息",
]


def pick_topic() -> str:
    # 用日期做随机种子, 同一天结果稳定, 不同天换话题
    today = datetime.date.today().isoformat()
    rnd = random.Random(today)
    return rnd.choice(TOPICS)


def generate_email(topic: str) -> dict:
    """调用 OpenAI(带联网搜索)生成 {subject, html_body}"""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    instructions = (
        "你是一名优秀的中文科技科普作者。请围绕给定话题, 先用联网搜索找 2-4 篇高质量、"
        "可信、面向大众的科普文章或权威资料(中英文皆可), 再据此写一篇通俗易懂但有深度的"
        "中文科普(术语可中英夹杂)。结构: 1) 一句话钩子; 2) 核心原理分 2-4 段循序渐进, "
        "善用类比; 3) 一个反直觉的冷知识; 4) 延伸阅读: 列出引用文章的标题+真实可点击链接。"
        "篇幅约 400-800 字, 适合早上几分钟读完。\n\n"
        "只输出一个 JSON 对象, 不要加 Markdown 代码块标记, 格式严格为:\n"
        '{"subject": "邮件主题(以【每日科技科普】开头)", "html_body": "完整的 HTML 正文"}\n'
        "html_body 用简单内联样式即可, 标题用 <h2>, 段落用 <p>, 链接用 <a href>。"
    )

    resp = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        instructions=instructions,
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
