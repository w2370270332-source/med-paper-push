#!/usr/bin/env python3
"""通过飞书 API 直接推送报告到飞书群."""

import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
REPORT_FILE = ROOT / "report.md"
TZ = timezone(timedelta(hours=8))

# Feishu app credentials (from environment variables)
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
LIST_CHATS_URL = "https://open.feishu.cn/open-apis/im/v1/chats"


def get_tenant_token() -> str | None:
    """获取 tenant access token."""
    try:
        resp = requests.post(TOKEN_URL, json={
            "app_id": APP_ID,
            "app_secret": APP_SECRET
        }, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["tenant_access_token"]
        print(f"[ERROR] Token 获取失败: {data}")
        return None
    except Exception as e:
        print(f"[ERROR] Token 请求异常: {e}")
        return None


def list_chats(token: str) -> list[dict]:
    """列出 bot 所在的群聊."""
    chats = []
    page_token = None
    try:
        while True:
            params = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(LIST_CHATS_URL, params=params,
                              headers={"Authorization": f"Bearer {token}"}, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[ERROR] 群列表获取失败: {data}")
                break
            chats.extend(data.get("data", {}).get("items", []))
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"]["page_token"]
    except Exception as e:
        print(f"[ERROR] 群列表请求异常: {e}")
    return chats


def send_text(token: str, chat_id: str, text: str) -> bool:
    """发送文本消息到指定群聊."""
    try:
        content = json.dumps({"text": text})
        resp = requests.post(MESSAGE_URL, params={"receive_id_type": "chat_id"}, json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": content
        }, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            return True
        print(f"[ERROR] 消息发送失败: {data}")
        return False
    except Exception as e:
        print(f"[ERROR] 消息请求异常: {e}")
        return False


def send_card(token: str, chat_id: str, title: str, summary: str, url: str | None = None) -> bool:
    """发送卡片消息."""
    elements = [{"tag": "markdown", "content": summary}]
    if url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看完整报告"},
                "type": "primary",
                "url": url
            }]
        })

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue"
        },
        "elements": elements
    }

    try:
        content = json.dumps(card)
        resp = requests.post(MESSAGE_URL, params={"receive_id_type": "chat_id"}, json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": content
        }, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            return True
        else:
            # 卡片发送失败时回退到文本
            print(f"[WARN] 卡片消息失败: {data.get('msg')}, 尝试文本")
            return send_text(token, chat_id, f"{title}\n\n{summary}")
    except Exception as e:
        print(f"[ERROR] 卡片请求异常: {e}")
        return False


def main():
    if not REPORT_FILE.exists():
        print(f"[ERROR] 报告文件不存在: {REPORT_FILE}")
        print("请先运行 generate_report.py 生成报告")
        return 1

    report = REPORT_FILE.read_text(encoding="utf-8")

    print("[1/3] 获取飞书 Token...")
    token = get_tenant_token()
    if not token:
        return 1
    print("  [OK] Token 获取成功")

    print("[2/3] 获取群聊列表...")
    chats = list_chats(token)
    if not chats:
        print("  [WARN] 未找到任何群聊，Bot 可能未被添加到群")
        return 1

    print(f"  [OK] 找到 {len(chats)} 个群:")
    for c in chats:
        print(f"    - {c.get('name', '(无名称)')} ({c['chat_id']})")

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    # 取报告开头部分作为推送摘要
    lines = report.split("\n")
    summary_lines = []
    in_focus = False
    for line in lines:
        if line.startswith("## 本周重点关注"):
            in_focus = True
            continue
        if in_focus:
            if line.startswith("---"):
                break
            if line.strip():
                summary_lines.append(line)

    summary = "\n".join(summary_lines[:30])
    if len(summary) > 3000:
        summary = summary[:3000] + "\n\n...\n(完整报告见 Obsidian 或邮箱)"

    print(f"[3/3] 推送报告到 {len(chats)} 个群...")
    success_count = 0
    for c in chats:
        name = c.get("name", c["chat_id"])
        if send_card(token, c["chat_id"], f"📚 预防医学与营养学文献周报 ({today})", summary):
            print(f"  [OK] {name}")
            success_count += 1
        else:
            print(f"  [FAIL] {name}")

    print(f"\n推送完成: {success_count}/{len(chats)} 个群成功")
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
