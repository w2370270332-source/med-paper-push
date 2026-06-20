#!/usr/bin/env python3
"""通过 QQ 邮箱 SMTP 发送报告到飞书群邮箱."""

import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / ".env.email.json"
REPORT_FILE = ROOT / "report.md"

TZ = timezone(timedelta(hours=8))


def load_config():
    """加载邮件配置（优先环境变量，回退到 JSON 配置文件）."""
    env_config = {
        "smtp_host": os.environ.get("EMAIL_SMTP_HOST"),
        "smtp_port": int(os.environ["EMAIL_SMTP_PORT"]) if os.environ.get("EMAIL_SMTP_PORT") else None,
        "sender_email": os.environ.get("EMAIL_SENDER"),
        "sender_password": os.environ.get("EMAIL_PASSWORD"),
        "receiver_email": os.environ.get("EMAIL_RECEIVER"),
    }
    if all(env_config.values()):
        return env_config

    if not CONFIG_FILE.exists():
        print(f"[ERROR] 邮件配置不存在: {CONFIG_FILE}")
        print(f"请创建 {CONFIG_FILE} 或设置环境变量 EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, "
              f"EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER")
        return None

    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def send_email(config: dict, report: str) -> bool:
    """发送邮件."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"预防医学与营养学文献周报 ({today})", "utf-8")
    msg["From"] = config["sender_email"]
    msg["To"] = config["receiver_email"]

    # 纯文本 + HTML 双版本
    plain = report[:2000] + "\n\n...\n(完整报告见附件或查看原文)"
    html = markdown_to_html(report)

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(config["smtp_host"], config["smtp_port"]) as server:
            server.login(config["sender_email"], config["sender_password"])
            server.sendmail(config["sender_email"], config["receiver_email"], msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        print("[ERROR] SMTP 认证失败，请检查 QQ 邮箱授权码是否正确")
        print("  获取授权码：QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码")
        return False
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}")
        return False


def markdown_to_html(md: str) -> str:
    """简易 Markdown → HTML 转换."""
    import re

    lines = md.split("\n")
    html_lines = []
    in_table = False
    in_list = False

    for line in lines:
        # 标题
        if line.startswith("### "):
            html_lines.append(f'<h3>{line[4:]}</h3>')
            continue
        elif line.startswith("## "):
            html_lines.append(f'<h2>{line[3:]}</h2>')
            continue
        elif line.startswith("# "):
            html_lines.append(f'<h1>{line[2:]}</h1>')
            continue

        # 分割线
        if line.strip() == "---":
            html_lines.append("<hr>")
            continue

        # 表格
        if line.startswith("|") and line.endswith("|"):
            if not in_table:
                in_table = True
                html_lines.append('<table border="1" cellpadding="4" cellspacing="0">')
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.strip(":-") == "" for c in cells):
                continue  # 跳过分隔行
            tag = "th" if in_table and len(html_lines) > 0 and html_lines[-1].startswith("<table") else "td"
            html_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        elif in_table:
            html_lines.append("</table>")
            in_table = False

        # 粗体 / 斜体 / 链接 / 块引用
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', line)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)

        if line.startswith("> "):
            html_lines.append(f'<blockquote>{line[2:]}</blockquote>')
            continue

        if not line.strip():
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{line}</p>")

    if in_table:
        html_lines.append("</table>")

    return '\n'.join(html_lines)


def push_to_feishu_via_cc(config: dict, report_path: str) -> bool:
    """通过 cc-connect 飞书机器人直接推送报告摘要."""
    import subprocess

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    # 取报告前 800 字符作为推送摘要
    summary = Path(report_path).read_text(encoding="utf-8")[:800]

    message = f"📚 预防医学与营养学文献周报 ({today})\n\n{summary}\n\n📎 完整报告: {report_path}"

    try:
        result = subprocess.run(
            ["cc-connect", "send", "--project", "vs", "--message", message],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT)
        )
        if result.returncode == 0:
            return True
        else:
            print(f"  [WARN] cc-connect 发送失败: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  [WARN] cc-connect 未安装或不在 PATH")
        return False
    except Exception as e:
        print(f"  [WARN] cc-connect 错误: {e}")
        return False


def main():
    config = load_config()
    if not config:
        return 1

    if not REPORT_FILE.exists():
        print(f"[ERROR] 报告文件不存在: {REPORT_FILE}")
        print("请先运行 generate_report.py 生成报告")
        return 1

    report = REPORT_FILE.read_text(encoding="utf-8")

    print(f"[1/2] 发送邮件到 {config['receiver_email']}...")
    if send_email(config, report):
        print("  [OK] 邮件发送成功")
    else:
        print("  [FAIL] 邮件发送失败")

    print(f"[2/2] 推送到飞书...")
    if push_to_feishu_via_cc(config, str(REPORT_FILE)):
        print("  [OK] 飞书推送成功")
    else:
        print("  [SKIP] 飞书推送跳过（邮件方式已发送）")

    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
