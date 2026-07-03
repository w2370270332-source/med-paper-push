#!/usr/bin/env python3
"""研究生每日任务提醒 — 生成当日任务并推送到飞书.

基于 task_plan.md 的五阶段规划，根据当前日期自动判断所处阶段，
生成对应的每日任务清单，通过飞书 Bot API 推送到群聊。

运行方式:
  python daily_reminder.py          # 推送今日任务
  python daily_reminder.py --dry-run  # 仅打印，不推送
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows 控制台 UTF-8 支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))

# 飞书 API 配置
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
LIST_CHATS_URL = "https://open.feishu.cn/open-apis/im/v1/chats"

# ============================================================
# 阶段定义 — 根据 task_plan.md
# ============================================================

PHASES = [
    {"name": "阶段一：研一上学期", "start": "2026-09-01", "end": "2026-12-31",
     "focus": "适应节奏 · 健康改造启动 · 计算机二级"},
    {"name": "阶段二：研一下学期", "start": "2027-01-01", "end": "2027-06-30",
     "focus": "健康初见成效 · 英语六级550+ · 科研起步"},
    {"name": "阶段三：研二上学期", "start": "2027-07-01", "end": "2027-12-31",
     "focus": "健康达标 · SAS双证 · 科研产出"},
    {"name": "阶段四：研二下学期", "start": "2028-01-01", "end": "2028-06-30",
     "focus": "健康稳定 · 职业医师考试 · 论文发表"},
    {"name": "阶段五：研三", "start": "2028-07-01", "end": "2029-06-30",
     "focus": "毕业论文 · 考公考编 · 就业"},
]


def get_current_phase(today: datetime) -> dict:
    """根据日期判断当前阶段."""
    for phase in PHASES:
        start = datetime.strptime(phase["start"], "%Y-%m-%d").replace(tzinfo=TZ)
        end = datetime.strptime(phase["end"], "%Y-%m-%d").replace(tzinfo=TZ)
        if start <= today <= end:
            return phase
    # 入学前（2026年7-8月）
    pre_enrollment_end = datetime(2026, 8, 31, tzinfo=TZ)
    if today <= pre_enrollment_end:
        return {"name": "入学前准备期", "start": "2026-07-01", "end": "2026-08-31",
                "focus": "健康习惯建立 · 英语预热 · 计算机二级提前学"}
    return PHASES[-1]


def get_weekday_label(today: datetime) -> str:
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return labels[today.weekday()]


def is_rest_day(today: datetime) -> bool:
    """周日为完全休息日."""
    return today.weekday() == 6


def is_weekend(today: datetime) -> bool:
    return today.weekday() in (5, 6)


# ============================================================
# 每日任务生成
# ============================================================

def generate_health_tasks(today: datetime) -> list[str]:
    """生成当日健康任务."""
    tasks = []
    weekday = today.weekday()

    # 每日必做（非 negotiable）
    tasks.append("🧘 早起拉伸 10-15 分钟（靠墙站立 + 颈部拉伸 + 肩背弹力带）")
    tasks.append("🧴 晨间护肤（温和洁面 + 清爽乳液 + 防晒 SPF30+）")
    tasks.append("💧 全天饮水 2000ml（晨起一杯温水，餐前一杯）")

    # 运动（根据星期几轮换）
    if is_rest_day(today):
        tasks.append("😴 今日完全休息日，不安排运动")
    elif weekday in (0, 2, 4):  # 周一三五
        tasks.append("🏃 有氧运动 40 分钟（慢跑/快走/游泳）+ 运动后拉伸 5 分钟")
    elif weekday in (1, 3):  # 周二四
        tasks.append("💪 力量训练 30 分钟（自重或小重量，重点练背）+ 运动后拉伸")
    elif weekday == 5:  # 周六
        tasks.append("🧘 瑜伽或普拉提 1 次（重点背部+核心）")

    # 皮肤护理周期提醒
    if weekday in (0, 3):  # 周一、周四
        tasks.append("🧴 🏷️ 酮康唑洗剂洗头（脂溢性皮炎护理）")
    if weekday == 5:  # 周六
        tasks.append("🧽 温和去角质（鸡皮肤护理，水杨酸沐浴露或磨砂膏）")

    # 晚间
    tasks.append("🧴 晚间护肤（温和洁面 + 阿达帕林点涂痘痘 + 尿素身体乳涂四肢）")
    tasks.append("🛏️ 23:00 前入睡，保证 7-8 小时睡眠")

    return tasks


def generate_study_tasks(today: datetime, phase: dict) -> list[str]:
    """生成当日学习任务."""
    phase_name = phase["name"]
    tasks = []

    if is_rest_day(today):
        tasks.append("📖 自由阅读（不强制，可读英文文献或专业书籍）")
        return tasks

    # 英语 — 贯穿所有阶段
    tasks.append("🇬🇧 背单词 50 个 + 复习旧词（墨墨背单词）")
    tasks.append("🎧 英语影子跟读 15 分钟（新闻/学术讲座）")

    # 阶段特定任务
    if "入学前" in phase_name:
        tasks.append("💻 计算机二级 MS Office 真题练习 1 小时")
        if today.weekday() in (0, 3):  # 周一、周四
            tasks.append("📚 阅读公共卫生入门文献 1 篇")

    elif "阶段一" in phase_name:
        tasks.append("💻 计算机二级 MS Office 真题练习 1 小时（12月考试）")

    elif "阶段二" in phase_name:
        tasks.append("📝 英语六级：阅读 1 篇 + 听力 1 篇 + 翻译 1 篇")
        if today.weekday() == 5:  # 周六
            tasks.append("📋 六级真题完整模拟 1 套")
        if today.weekday() in (2, 5):  # 周三、周六
            tasks.append("🔬 阅读英文文献 1 篇，做笔记")
        tasks.append("📊 SAS 基础入门 30 分钟（数据步/过程步）")

    elif "阶段三" in phase_name:
        tasks.append("📊 SAS 学习 1.5 小时（进阶：宏编程/SQL/统计过程）")
        if today.weekday() in (0, 3):
            tasks.append("🔬 阅读英文文献 1 篇 + 论文写作 30 分钟")

    elif "阶段四" in phase_name:
        tasks.append("🏥 公共卫生职业医师复习 2 小时（按科目轮换）")
        if today.weekday() in (0, 2, 4):
            tasks.append("📝 医师考试刷题 1 小时")
        tasks.append("📄 论文写作 30 分钟")

    elif "阶段五" in phase_name:
        tasks.append("📝 行测练习 1 小时 + 申论练习 1 小时")
        tasks.append("📄 毕业论文推进 1 小时")

    return tasks


def generate_weekly_focus(phase: dict) -> list[str]:
    """生成本周重点关注."""
    return [
        f"🎯 当前阶段：{phase['name']}",
        f"📌 阶段重点：{phase['focus']}",
        "✅ 本周最低目标：有氧×3 | 力量×2 | 体态×4 | 完全休息×1",
        "📅 周日晚 30 分钟复盘本周完成情况",
    ]


# ============================================================
# 励志语录池
# ============================================================

QUOTES = [
    ("不积跬步，无以至千里；不积小流，无以成江海。", "荀子《劝学》"),
    ("每一个不曾起舞的日子，都是对生命的辜负。", "尼采"),
    ("自律给我自由。", "康德"),
    ("种一棵树最好的时间是十年前，其次是现在。", "非洲谚语"),
    ("天下难事，必作于易；天下大事，必作于细。", "老子《道德经》"),
    ("身体是革命的本钱。", "毛泽东"),
    ("苟日新，日日新，又日新。", "《礼记·大学》"),
    ("The best time to plant a tree was 20 years ago. The second best time is now.", "Chinese Proverb"),
    ("千里之行，始于足下。", "老子《道德经》"),
    ("业精于勤，荒于嬉；行成于思，毁于随。", "韩愈《进学解》"),
    ("合抱之木，生于毫末；九层之台，起于累土。", "老子《道德经》"),
    ("你若盛开，蝴蝶自来。", "——"),
    ("锲而不舍，金石可镂。", "荀子《劝学》"),
    ("健康是智慧的条件，快乐的标志。", "爱默生"),
    ("积土成山，风雨兴焉；积水成渊，蛟龙生焉。", "荀子《劝学》"),
    ("成功不是将来才有的，而是从决定去做的那一刻起，持续累积而成。", "——"),
    ("盛年不重来，一日难再晨。及时当勉励，岁月不待人。", "陶渊明《杂诗》"),
    ("学如逆水行舟，不进则退。", "《增广贤文》"),
    ("志之所趋，无远弗届；穷山距海，不能限也。", "《格言联璧》"),
    ("你今天的努力，是明天幸运的伏笔。", "——"),
    ("博学之，审问之，慎思之，明辨之，笃行之。", "《中庸》"),
    ("路漫漫其修远兮，吾将上下而求索。", "屈原《离骚》"),
    ("宝剑锋从磨砺出，梅花香自苦寒来。", "《警世贤文》"),
    ("世上无难事，只要肯登攀。", "毛泽东"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("心之所向，素履以往；生如逆旅，一苇以航。", "七堇年"),
    ("天行健，君子以自强不息。", "《周易》"),
    ("日日行，不怕千万里；常常做，不怕千万事。", "《格言联璧》"),
    ("勿以善小而不为，勿以恶小而为之。", "刘备"),
    ("读书破万卷，下笔如有神。", "杜甫"),
]

REST_DAY_QUOTES = [
    ("休息不是偷懒，是为了走更远的路。", "——"),
    ("一张一弛，文武之道也。", "《礼记》"),
    ("懂得休息的人，才懂得工作。", "列宁"),
    ("劳逸结合，张弛有度。", "——"),
    ("Rest is not idleness.", "John Lubbock"),
    ("静以修身，俭以养德。", "诸葛亮《诫子书》"),
    ("Take rest; a field that has rested gives a bountiful crop.", "Ovid"),
]


def get_quote(today: datetime) -> str:
    """根据日期选取励志语录（固定索引，保证同一天多次运行一致）."""
    if is_rest_day(today):
        pool = REST_DAY_QUOTES
    else:
        pool = QUOTES
    idx = today.toordinal() % len(pool)
    text, author = pool[idx]
    return f"*{text}*\n—— {author}"


# ============================================================
# 飞书卡片消息构建
# ============================================================

def build_card(today: datetime, health: list[str], study: list[str],
               weekly: list[str], phase: dict, is_rest: bool) -> dict:
    """构建飞书卡片消息."""

    date_str = today.strftime("%Y年%m月%d日")
    weekday = get_weekday_label(today)
    emoji = "☀️" if not is_rest else "😴"
    week_num = today.isocalendar()[1]

    # 任务转为 checkbox 格式
    health_md = "\n".join(f"- [ ] {t}" for t in health)
    study_md = "\n".join(f"- [ ] {t}" for t in study)
    weekly_md = "\n".join(weekly)
    quote_text = get_quote(today)

    # 运动类型标签
    workout_label = _get_workout_label(today, is_rest)

    # 底部提示
    if is_rest:
        greeting = "💤 早安！今天是休息日，好好放松，给身心充电。"
    else:
        greeting = "☀️ 早安！新的一天，向目标靠近。"

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": f"{emoji} 每日任务提醒 — {date_str} {weekday}"},
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{greeting}**\n{phase['name']} · 第{week_num}周 · {phase['focus']}"}
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🏥 健康习惯（每日必做）**\n{health_md}"}
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**📚 学习任务**\n{study_md}"}
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🏃 今日运动：{workout_label}**\n{weekly_md}"}
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**💬 今日一言**\n{quote_text}"}
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": "🤖 每天 7:00 自动推送 · GitHub Actions · 完成后可长按编辑打勾"}]
            }
        ]
    }
    return card


def _get_workout_label(today: datetime, is_rest: bool) -> str:
    if is_rest:
        return "休息日"
    labels = {0: "有氧日", 1: "力量日", 2: "有氧日", 3: "力量日", 4: "有氧日", 5: "瑜伽/体态日"}
    return labels.get(today.weekday(), "—")


# ============================================================
# 飞书 API 操作
# ============================================================

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
        print(f"[ERROR] Token 获取失败: {data}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Token 请求异常: {e}", file=sys.stderr)
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
                print(f"[ERROR] 群列表获取失败: {data}", file=sys.stderr)
                break
            chats.extend(data.get("data", {}).get("items", []))
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"]["page_token"]
    except Exception as e:
        print(f"[ERROR] 群列表请求异常: {e}", file=sys.stderr)
    return chats


def send_card(token: str, chat_id: str, card: dict) -> bool:
    """发送卡片消息到指定群聊."""
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
        print(f"[ERROR] 卡片消息发送失败: {data}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] 消息请求异常: {e}", file=sys.stderr)
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    dry_run = "--dry-run" in sys.argv

    today = datetime.now(TZ)
    phase = get_current_phase(today)
    is_rest = is_rest_day(today)

    # 生成任务
    health = generate_health_tasks(today)
    study = generate_study_tasks(today, phase)
    weekly = generate_weekly_focus(phase)
    card = build_card(today, health, study, weekly, phase, is_rest)

    if dry_run:
        print("=" * 60)
        print(f"  DRY RUN — {today.strftime('%Y-%m-%d %H:%M')} {get_weekday_label(today)}")
        print(f"  阶段: {phase['name']} | 重点: {phase['focus']}")
        print(f"  休息日: {'是' if is_rest else '否'}")
        print("=" * 60)
        print("\n🏥 健康任务:")
        for t in health:
            print(f"  {t}")
        print("\n📚 学习任务:")
        for t in study:
            print(f"  {t}")
        print("\n📋 本周关注:")
        for t in weekly:
            print(f"  {t}")
        print("\n[DRY RUN] 未实际推送到飞书")
        return 0

    # 验证凭证
    if not APP_ID or not APP_SECRET:
        print("[ERROR] 未设置 FEISHU_APP_ID 或 FEISHU_APP_SECRET", file=sys.stderr)
        return 1

    print(f"[1/3] 生成每日任务 — {today.strftime('%Y-%m-%d')} {get_weekday_label(today)}")
    print(f"  阶段: {phase['name']}")
    print(f"  健康任务: {len(health)} 项")
    print(f"  学习任务: {len(study)} 项")

    print("[2/3] 获取飞书 Token...")
    token = get_tenant_token()
    if not token:
        return 1
    print("  [OK]")

    print("[3/3] 获取群聊并推送...")
    chats = list_chats(token)
    if not chats:
        print("  [WARN] 未找到任何群聊，Bot 可能未被添加到群")
        return 1

    success = 0
    for c in chats:
        name = c.get("name", c["chat_id"])
        if send_card(token, c["chat_id"], card):
            print(f"  [OK] {name}")
            success += 1
        else:
            print(f"  [FAIL] {name}")

    print(f"\n推送完成: {success}/{len(chats)} 个群成功")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
