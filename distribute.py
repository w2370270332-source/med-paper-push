#!/usr/bin/env python3
"""分发引擎 — 按用户偏好匹配论文并发送个性化推送."""

import html
import json
import os
import re
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


def _match_papers(areas: list[str], quartiles: list[str],
                  min_relevance_score: int = 1) -> list[dict]:
    """从论文池中匹配用户偏好（仅最近 36 小时入库的论文）."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
    papers = _supa(
        f"paper_pool?select=*&fetched_at=gte.{cutoff}"
        f"&relevance_score=gte.{min_relevance_score}"
        f"&order=pub_date.desc&limit=200"
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


def render_html_email(papers: list[dict], user_email: str, date_str: str) -> str:
    """Render paper list into mobile-friendly academic HTML email."""

    def _h(text: str) -> str:
        return html.escape(str(text), quote=False)

    def _stars(n: int) -> str:
        return "".join("★" if i < n else "☆" for i in range(10))

    def _clean_source(source: str) -> str:
        return re.sub(r"^.*?→\s*", "", source.strip()) or source.strip()

    annotated = sorted(
        [(p, p.get("relevance_score") or 5) for p in papers],
        key=lambda x: x[1], reverse=True
    )

    areas_set = set()
    for p in papers:
        a = (p.get("research_area") or "").strip()
        if a:
            areas_set.add(a)
    scope = "、".join(sorted(areas_set)) if areas_set else "预防医学与营养学"

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.7;color:#1a1a2e;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;">
<tr><td align="center" style="padding:32px 16px;">
<div style="max-width:640px;width:100%;margin:0 auto;">

<div style="background:linear-gradient(135deg,#1a365d,#2a4a7f);border-radius:12px;padding:32px 28px;margin-bottom:24px;color:#fff;">
<h1 style="margin:0 0 6px;font-size:22px;font-weight:700;">预防医学与营养学文献推送</h1>
<p style="margin:0 0 2px;font-size:14px;opacity:0.85;">{_h(date_str)}</p>
<p style="margin:0;font-size:13px;opacity:0.7;">覆盖领域：{_h(scope)}</p>
<div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.15);font-size:13px;">
<span style="display:inline-block;background:rgba(255,255,255,0.15);border-radius:20px;padding:4px 14px;font-weight:600;">共 {len(papers)} 篇</span>
</div>
</div>
""")

    for idx, (paper, score) in enumerate(annotated, 1):
        title_cn = (paper.get("title_cn") or "").strip()
        original_title = (paper.get("original_title") or "").strip()
        source_raw = (paper.get("source") or "").strip()
        source_clean = _clean_source(source_raw)
        authors = paper.get("authors", [])
        if isinstance(authors, list) and authors:
            author_str = ", ".join(a.get("name", "") for a in authors[:5])
        else:
            author_str = ""
        volume = (paper.get("volume") or "").strip()
        issue = (paper.get("issue") or "").strip()
        pages = (paper.get("pages") or "").strip()
        url = (paper.get("url") or "").strip()
        pmid = (paper.get("pmid") or "").strip()
        background = (paper.get("background") or "").strip()
        findings = (paper.get("findings") or "").strip()
        significance = (paper.get("significance") or "").strip()

        citation = source_clean or source_raw
        if volume:
            citation += f" {volume}"
            if issue:
                citation += f"({issue})"
            if pages:
                citation += f":{pages}"

        star_html = _stars(score)

        parts.append(f"""<div style="background:#fff;border-radius:10px;padding:24px;margin-bottom:16px;border:1px solid #e2e6ec;">

<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:14px;">
<span style="flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:#1a365d;color:#fff;border-radius:50%;font-size:13px;font-weight:700;">{idx}</span>
<div style="flex:1;min-width:0;">
<h2 style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1a365d;line-height:1.5;">{_h(title_cn)}</h2>
<p style="margin:0;font-size:13px;color:#5a6a7a;font-style:italic;">{_h(original_title)}</p>
</div>
</div>

<div style="margin-bottom:12px;font-size:13px;color:#5a6a7a;">
<span style="font-weight:600;color:#3a4a5a;">来源：</span>{_h(author_str + ("." if author_str else "") + " " + citation if author_str else citation)}
</div>

<div style="margin-bottom:12px;font-size:13px;">
<span style="color:#5a6a7a;font-weight:600;">相关度：</span>
<span style="color:#e6a817;letter-spacing:1px;">{star_html}</span>
<span style="color:#8a9aaa;font-size:12px;margin-left:4px;">({score}/10)</span>
</div>
""")
        if url:
            parts.append(f'<div style="margin-bottom:12px;font-size:13px;"><span style="color:#5a6a7a;font-weight:600;">DOI：</span><a href="{html.escape(url, quote=True)}" target="_blank" style="color:#2563eb;text-decoration:none;word-break:break-all;">{_h(url)}</a></div>\n')
        if pmid:
            url_abs = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
            parts.append(f'<div style="margin-bottom:12px;font-size:13px;"><span style="color:#5a6a7a;font-weight:600;">PMID：</span><a href="{html.escape(url_abs, quote=True)}" target="_blank" style="color:#2563eb;text-decoration:none;">{_h(pmid)}</a></div>\n')
        if background:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #4a90d9;"><div style="font-size:11px;font-weight:700;color:#4a90d9;margin-bottom:4px;">研究背景</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(background)}</p></div>\n')
        if findings:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #16a34a;"><div style="font-size:11px;font-weight:700;color:#16a34a;margin-bottom:4px;">核心发现</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(findings)}</p></div>\n')
        if significance:
            parts.append(f'<div style="margin-bottom:0;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #9333ea;"><div style="font-size:11px;font-weight:700;color:#9333ea;margin-bottom:4px;">研究意义</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(significance)}</p></div>\n')
        parts.append("</div>\n")

    parts.append(f"""<div style="text-align:center;padding:20px 16px 8px;">
<p style="margin:0 0 4px;font-size:12px;color:#9aabba;">由文献推送系统自动生成</p>
<p style="margin:0 0 4px;font-size:12px;color:#9aabba;">{_h(date_str)}</p>
<p style="margin:0;font-size:11px;color:#bacbd0;">{_h(user_email)}</p>
</div>

</div>
</td></tr>
</table>
</body>
</html>""")
    return "\n".join(parts)


def send_email(to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEText(body, "html", "utf-8")
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
    users = _supa("rpc/get_user_info") or []
    users = [u for u in users if u.get("enabled")]
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
        min_relevance = u.get("relevance_threshold") or 1

        papers = _match_papers(areas, quartiles, min_relevance)
        if not papers:
            continue

        if not _should_send_now(push_time, push_freq, push_days, last_push, True):
            continue

        date_str = datetime.now(TZ).strftime("%Y-%m-%d（%A）")
        report = render_html_email(papers, email, date_str)
        subject = f"预防医学与营养学文献推送 ({datetime.now(TZ).strftime('%Y-%m-%d')})"

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
        min_relevance = r.get("relevance_threshold") or 1

        papers = _match_papers(areas, quartiles, min_relevance)
        if not papers:
            continue

        if not _should_send_now(push_time, push_freq, push_days, last_push, True):
            continue

        date_str = datetime.now(TZ).strftime("%Y-%m-%d（%A）")
        report = render_html_email(papers, email, date_str)
        subject = f"预防医学与营养学文献推送 ({datetime.now(TZ).strftime('%Y-%m-%d')})"

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
