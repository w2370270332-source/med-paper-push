#!/usr/bin/env python3
"""分发引擎 — 按用户偏好匹配论文并发送个性化推送."""

import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "465"))
SMTP_USER = os.environ.get("EMAIL_SENDER", "")
SMTP_PASS = os.environ.get("EMAIL_PASSWORD", "")

# 研究领域 → 关键词映射（用于论文匹配）
AREA_KEYWORDS = {
    "肥胖与代谢": ["肥胖", "减重", "bmi", "体重", "代谢", "obesity", "adipose", "weight"],
    "心血管与代谢疾病": ["心血管", "心脏病", "血压", "高血压", "动脉硬化", "cardiovascular", "hypertension", "blood pressure", "heart"],
    "肠道菌群": ["肠道", "菌群", "微生物", "肠道菌", "microbiome", "microbiota", "gut", "flora"],
    "糖尿病与血糖管理": ["糖尿病", "血糖", "胰岛素", "t2dm", "diabetes", "glucose", "insulin"],
    "营养流行病学": ["流行病学", "队列", "观察", "epidemiology", "cohort", "population"],
    "公共卫生营养": ["公共卫生", "政策", "指南", "public health", "policy", "guideline"],
    "母婴营养": ["母婴", "孕期", "妊娠", "母乳", "婴幼儿", "maternal", "pregnancy", "lactation", "infant"],
    "衰老与营养": ["衰老", "老龄", "老年", "aging", "elderly", "older"],
    "食品政策与安全": ["食品政策", "食品安全", "食物安全", "food policy", "food safety"],
    "膳食干预与临床营养": ["膳食", "饮食", "干预", "临床营养", "diet", "dietary", "intervention", "clinical nutrition"],
    "营养生物化学": ["营养素", "生物化学", "维生素", "矿物质", "nutrient", "biochemistry", "vitamin", "mineral"],
    "流行病学": ["流行病学", "发病率", "患病率", "风险因素", "epidemiology", "incidence", "prevalence", "risk factor"],
    "生物统计学": ["统计", "方法学", "数据", "模型", "statistics", "biostatistics", "methodology", "model"],
    "AI驱动的健康研究": ["机器学习", "深度学习", "人工智能", "预测模型", "machine learning", "deep learning", "AI", "prediction"],
    "药食同源与植物化学物": ["药食同源", "植物化学", "类黄酮", "黄酮", "多酚", "柑橘", "柚皮苷", "橙皮苷", "生物活性成分", "天然产物", "flavonoid", "polyphenol", "citrus", "naringin", "hesperidin", "phytochemical", "bioactive", "medicinal food", "functional food"],
    "高尿酸血症与痛风": ["高尿酸", "尿酸", "痛风", "嘌呤", "黄嘌呤氧化酶", "hyperuricemia", "uric acid", "gout", "purine", "xanthine oxidase"],
    "炎症与免疫调节": ["炎症", "抗炎", "免疫", "细胞因子", "炎症因子", "抗炎活性", "inflammation", "anti-inflammatory", "immune", "cytokine", "inflammatory", "NF-kB", "NLRP3"],
}


def _supa(path: str, method: str = "GET", body: dict | None = None) -> list | dict | None:
    """通用 Supabase REST 请求."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            return json.loads(text) if text else None
    except Exception as e:
        print(f"  [WARN] {path}: {e}")
        return None


def _match_papers(areas: list[str], quartiles: list[str]) -> list[dict]:
    """从论文池中匹配用户偏好（仅最近 36 小时入库的论文）."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
    papers = _supa(
        f"paper_pool?select=*&fetched_at=gte.{cutoff}&order=pub_date.desc&limit=200"
    ) or []
    if not papers:
        print("  [INFO] 最近 36 小时无新论文入库")
        return []
    if not areas:
        return papers[:20]

    matched = []
    for p in papers:
        combined = ((p.get("title_cn") or "") + " " + (p.get("title") or "") + " " +
                    (p.get("findings") or "") + " " + (p.get("abstract") or "")).lower()
        for area in areas:
            keywords = AREA_KEYWORDS.get(area, [])
            if any(kw in combined for kw in keywords):
                matched.append(p)
                break
    return matched[:20]


def _generate_report(papers: list[dict], name: str = "") -> str:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now(TZ).weekday()]
    lines = [
        f"# 预防医学与营养学文献推送",
        f"**{today}（{weekday}）** | 匹配到 {len(papers)} 篇",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(papers, 1):
        title = p.get("title_cn") or p.get("title", "")
        original_title = p.get("original_title") or p.get("title", "")
        source = p.get("source", "")
        pmid = p.get("pmid") or ""
        url = p.get("url") or ""
        background = p.get("background") or ""
        methods = p.get("methods") or ""
        findings = p.get("findings") or ""
        significance = p.get("significance") or ""
        limitation = p.get("limitation") or ""
        relevance = p.get("relevance") or ""

        lines.append(f"## {i}. {title}")
        lines.append("")
        if original_title and original_title != title:
            lines.append(f"*{original_title}*")
        lines.append(f"**来源：**{source}")
        if pmid:
            lines.append(f"**PMID：**[{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
        if url:
            lines.append(f"**DOI：**[{url}]({url})")
        lines.append("")
        if background:
            lines.append(f"**背景：**{background}")
            lines.append("")
        if methods:
            lines.append(f"**方法：**{methods}")
            lines.append("")
        if findings:
            lines.append(f"**发现：**{findings}")
            lines.append("")
        if significance:
            lines.append(f"**意义：**{significance}")
            lines.append("")
        if limitation:
            lines.append(f"**局限：**{limitation}")
            lines.append("")
        if relevance:
            lines.append(f"**关联：**{relevance}")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*由文献推送系统自动生成于 {today}*")
    return "\n".join(lines)


def send_email(to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"  [ERROR] 发送失败 ({to}): {e}")
        return False


def _should_send_now(push_time: str, push_freq: str, push_days: list[str],
                     last_push: str | None, has_papers: bool = False) -> bool:
    """每天仅发一次：到达推送时间后首次匹配论文即发送，同日不重复."""
    force = bool(os.environ.get("DISTRIBUTE_FORCE"))
    now = datetime.now(TZ)

    # 今天已推送过 → 阻止
    if last_push:
        last = datetime.fromisoformat(last_push.replace("Z", "+00:00"))
        last_cn = last.astimezone(TZ)
        if last_cn.date() == now.date():
            return False

    if force:
        return True

    # 无可用论文 → 不发送
    if not has_papers:
        return False

    # 检查推送频率
    weekday = str(now.weekday() + 1)
    if push_freq == "weekdays" and push_days and weekday not in push_days:
        return False
    if push_freq == "weekly" and weekday != "1":
        return False

    # 到达或超过推送时间 → 发送
    try:
        h, m = map(int, push_time.split(":"))
        push_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now >= push_dt:
            return True
    except (ValueError, AttributeError):
        pass

    return False


def process_users():
    """处理注册用户."""
    users = _supa("user_info?select=*&enabled=is.true") or []
    print(f"[users] {len(users)} 活跃用户")

    sent = 0
    for u in users:
        user_id = u.get("user_id", "")
        email = u.get("email", "")
        if not email:
            continue

        # 获取上次推送时间
        history = _supa(
            f"push_history?select=pushed_at&user_id=eq.{user_id}"
            f"&order=pushed_at.desc&limit=1"
        ) or []
        last_push = history[0].get("pushed_at") if history else None

        push_time = u.get("push_time") or "08:00"
        push_freq = u.get("push_frequency") or "daily"
        push_days = u.get("push_days") or []

        areas = u.get("research_areas") or []
        quartiles = u.get("cas_quartiles") or ["1", "2", "3", "4"]

        papers = _match_papers(areas, quartiles)
        if not papers:
            continue

        if not _should_send_now(push_time, push_freq, push_days, last_push, True):
            continue

        report = _generate_report(papers, email)
        subject = f"📚 预防医学与营养学文献推送 ({datetime.now(TZ).strftime('%Y-%m-%d')})"

        if send_email(email, subject, report):
            # 记录推送历史
            _supa("push_history", "POST", {
                "user_id": user_id,
                "paper_ids": [p["id"] for p in papers],
                "paper_count": len(papers),
                "report_content": report[:5000],
            })
            sent += 1
            print(f"  [OK] {email} ({len(papers)}篇)")

    return sent


def process_recipients():
    """处理直接添加的邮箱."""
    recipients = _supa("email_recipients?select=*") or []
    print(f"[recipients] {len(recipients)} 个")

    sent = 0
    for r in recipients:
        email = r.get("email", "")
        if not email:
            continue

        # 获取上次推送时间（用 email 作为标识）
        history = _supa(
            f"push_history?select=pushed_at&report_content=ilike.*{email}*"
            f"&order=pushed_at.desc&limit=1"
        ) or []
        last_push = history[0].get("pushed_at") if history else None

        push_time = r.get("push_time") or "08:00"
        push_freq = r.get("push_frequency") or "daily"
        push_days = r.get("push_days") or []

        areas = r.get("research_areas") or []
        quartiles = r.get("cas_quartiles") or ["1", "2", "3", "4"]

        papers = _match_papers(areas, quartiles)
        if not papers:
            continue

        if not _should_send_now(push_time, push_freq, push_days, last_push, True):
            continue

        report = _generate_report(papers, email)
        subject = f"📚 预防医学与营养学文献推送 ({datetime.now(TZ).strftime('%Y-%m-%d')})"

        if send_email(email, subject, report):
            _supa("push_history", "POST", {
                "user_id": None,
                "paper_ids": [p["id"] for p in papers],
                "paper_count": len(papers),
                "report_content": f"Recipient: {email}\n\n{report[:5000]}",
            })
            sent += 1
            print(f"  [OK] {email} ({len(papers)}篇)")

    return sent


def main():
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    print(f"分发引擎启动 — {now}")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] 缺少 Supabase 配置")
        return 1

    user_sent = process_users()
    recipient_sent = process_recipients()

    print(f"\n分发完成: 用户 {user_sent} + 直接邮箱 {recipient_sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
