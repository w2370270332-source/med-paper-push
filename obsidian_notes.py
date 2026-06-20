#!/usr/bin/env python3
"""生成 Obsidian 兼容的文献笔记和知识库结构."""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OBSIDIAN_ROOT = ROOT / "obsidian"
INBOX = OBSIDIAN_ROOT / "文献收件箱"
WEEKLY = OBSIDIAN_ROOT / "周报"
TOPICS = OBSIDIAN_ROOT / "主题索引"
TZ = timezone(timedelta(hours=8))


def slug(text: str, max_len: int = 50) -> str:
    """生成文件名安全的 slug."""
    import re
    s = re.sub(r'[^\w\s-]', '', text.lower())
    s = re.sub(r'[-\s]+', '-', s).strip('-')
    return s[:max_len]


def write_paper_note(p: dict, date_str: str) -> Path | None:
    """为单篇论文创建 Obsidian 笔记."""
    pmid = p.get("pmid", "")
    title_cn = p.get("title_cn", "") or p.get("original_title", "")
    if not pmid and not title_cn:
        return None

    # 文件名
    if pmid:
        filename = f"PMID{pmid}.md"
    else:
        filename = f"{slug(title_cn, 40)}.md"

    # 日期子目录
    day_dir = INBOX / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    filepath = day_dir / filename

    if filepath.exists():
        return filepath  # 已存在，跳过（可能在多源抓取中重复）

    source = p.get("source", "")
    url = p.get("url", "")
    original_title = p.get("original_title", "") or p.get("title_cn", "")
    study_type = p.get("study_type", "")
    background = p.get("background", "")
    methods = p.get("methods", "")
    findings = p.get("findings", "")
    significance = p.get("significance", "")
    limitation = p.get("limitation", "")
    relevance = p.get("relevance", "")

    # Tags 推导
    tags = ["文献"]
    combined = (original_title + " " + findings + " " + significance).lower()
    tag_map = {
        "肥胖": "肥胖", "obesity": "肥胖", "减重": "肥胖", "bmi": "肥胖",
        "肠道": "肠道菌群", "microbiome": "肠道菌群", "microbiota": "肠道菌群", "gut": "肠道菌群",
        "营养": "营养", "nutrition": "营养", "diet": "营养", "饮食": "营养",
        "心血管": "心血管", "cardiovascular": "心血管",
        "糖尿病": "糖尿病", "diabetes": "糖尿病", "t2dm": "糖尿病",
        "代谢": "代谢", "metabolic": "代谢",
        "预防": "预防医学", "prevention": "预防医学",
        "流行病": "流行病学", "epidemiology": "流行病学",
        "公共": "公共卫生", "public health": "公共卫生",
        "炎症": "炎症", "inflammation": "炎症",
        "肿瘤": "肿瘤", "cancer": "肿瘤",
        "衰老": "衰老", "aging": "衰老",
        "rct": "RCT", "随机": "RCT", "trial": "临床试验",
        "meta": "Meta分析", "systematic review": "系统综述",
        "cohort": "队列研究",
    }
    for kw, tag in tag_map.items():
        if kw in combined:
            tags.append(tag)

    tags = list(dict.fromkeys(tags))[:8]  # 去重，最多 8 个
    tags_str = ", ".join(tags)
    tag_links = " ".join(f"#{t.replace(' ', '')}" for t in tags)

    # 构建笔记
    lines = [
        "---",
        f"pmid: {pmid}",
        f"title: \"{original_title[:120]}\"",
        f"title_cn: \"{title_cn[:120]}\"",
        f"source: \"{source}\"",
        f"url: \"{url}\"",
        f"date: {date_str}",
        f"type: {study_type}",
        f"tags: [{tags_str}]",
        "---",
        "",
        tag_links,
        "",
        f"# {title_cn or original_title}",
        "",
        f"**原文：**{original_title}",
        f"**来源：**{source}",
    ]

    if pmid:
        lines.append(f"**PubMed：**[PMID:{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
    if url:
        lines.append(f"**链接：**[DOI]({url})")
    lines.append("")

    if background:
        lines.append("## 研究背景")
        lines.append(background)
        lines.append("")
    if methods:
        lines.append("## 方法")
        lines.append(methods)
        lines.append("")
    if findings:
        lines.append("## 核心发现")
        lines.append(findings)
        lines.append("")
    if significance:
        lines.append("## 意义")
        lines.append(significance)
        lines.append("")
    if limitation:
        lines.append("## 局限性")
        lines.append(limitation)
        lines.append("")
    if relevance:
        lines.append("## 与研究方向关联")
        lines.append(relevance)
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def write_daily_moc(date_str: str, papers: list[dict], note_paths: list[Path]) -> Path:
    """生成每日文献索引 (MOC)."""
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        datetime.strptime(date_str, "%Y-%m-%d").weekday()
    ]
    filepath = INBOX / f"{date_str}.md"

    lines = [
        "---",
        f"date: {date_str}",
        "type: daily-moc",
        f"tags: [文献收件箱, 日报]",
        "---",
        "",
        f"# 文献收件箱 — {date_str}（{weekday}）",
        "",
        f"共 {len(papers)} 篇文献，其中 {len(note_paths)} 篇已生成独立笔记。",
        "",
        "## 文献列表",
        "",
    ]

    for p in papers:
        title_cn = p.get("title_cn", "") or p.get("original_title", "")
        findings = p.get("findings", "")
        pmid = p.get("pmid", "")
        source = p.get("source", "")

        note_link = ""
        if pmid:
            note_link = f"[[文献收件箱/{date_str}/PMID{pmid}|→ 笔记]]"

        lines.append(f"### {title_cn}")
        lines.append(f"**{source}** {note_link}")
        if findings:
            lines.append(f"{findings[:200]}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def write_weekly_note(result: dict, start_date: str, end_date: str) -> Path:
    """生成周度综述 Obsidian 笔记."""
    week_num = datetime.strptime(end_date, "%Y-%m-%d").isocalendar()[1]
    year = end_date[:4]
    filepath = WEEKLY / f"{year}-W{week_num:02d}.md"

    headline = result.get("headline", "")
    sections = result.get("sections", [])
    trends = result.get("trends", [])
    gaps = result.get("research_gaps", [])
    spotlight = result.get("spotlight", "")
    meta = result.get("_meta", {})

    lines = [
        "---",
        f"date: {end_date}",
        f"week: {year}-W{week_num:02d}",
        f"range: {start_date} → {end_date}",
        f"total_papers: {meta.get('total_papers', 0)}",
        f"analyzed_papers: {meta.get('analyzed_papers', 0)}",
        "type: weekly-review",
        "tags: [周报, 文献综述]",
        "---",
        "",
        f"# 文献周报 — {year} 第 {week_num} 周",
        "",
        f"**{start_date} → {end_date}** | 共 {meta.get('total_papers', '?')} 篇",
        "",
    ]

    if headline:
        lines.append(f"> **📌 {headline}**")
        lines.append("")

    for section in sections:
        theme = section.get("theme", "")
        summary = section.get("summary", "")
        key_papers = section.get("key_papers", [])
        if not theme:
            continue
        lines.append(f"## {theme}")
        lines.append("")
        if summary:
            lines.append(summary)
            lines.append("")
        for kp in key_papers:
            lines.append(f"- **{kp.get('title_cn', '')}** — {kp.get('takeaway', '')}")
        lines.append("")

    if trends:
        lines.append("## 趋势判断")
        lines.append("")
        for t in trends:
            lines.append(f"- {t}")
        lines.append("")

    if gaps:
        lines.append("## 研究空白")
        lines.append("")
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")

    if spotlight:
        lines.append("## 本周精读推荐")
        lines.append("")
        lines.append(spotlight)
        lines.append("")

    lines.append("---")
    lines.append(f"*生成于 {meta.get('generated_at', '')} · 模型：{meta.get('model', '')}*")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def update_topic_index(papers: list[dict]) -> None:
    """更新主题索引（增量追加）."""
    topic_map: dict[str, list[str]] = {}
    tag_map = {
        "肥胖": ["肥胖", "obesity", "减重", "bmi", "weight loss"],
        "肠道菌群": ["microbiome", "microbiota", "gut", "flora"],
        "营养": ["nutrition", "diet", "dietary", "nutrient", "food"],
        "心血管": ["cardiovascular", "heart", "hypertension", "blood pressure"],
        "糖尿病": ["diabetes", "t2dm", "glucose", "insulin"],
        "代谢": ["metabolic", "metabolism"],
        "预防医学": ["prevention", "preventive"],
        "流行病学": ["epidemiology", "cohort", "population"],
        "公共卫生": ["public health", "policy"],
    }

    for p in papers:
        title_cn = p.get("title_cn", "") or p.get("original_title", "")
        findings = p.get("findings", "")
        pmid = p.get("pmid", "")
        date = p.get("date", "") or datetime.now(TZ).strftime("%Y-%m-%d")
        combined = (title_cn + " " + findings).lower()

        for topic, keywords in tag_map.items():
            if any(kw in combined for kw in keywords):
                if topic not in topic_map:
                    topic_map[topic] = []
                note_ref = f"[[文献收件箱/{date}/PMID{pmid}|{title_cn[:40]}]]" if pmid else title_cn[:40]
                entry = f"- {note_ref} — {findings[:100]}"
                if entry not in topic_map[topic]:
                    topic_map[topic].append(entry)

    TOPICS.mkdir(parents=True, exist_ok=True)

    for topic, entries in topic_map.items():
        filepath = TOPICS / f"{topic}.md"
        existing: list[str] = []
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8").split("\n")

        # 只追加新条目
        new_entries = [e for e in entries if e not in existing]
        if not new_entries:
            continue

        if not filepath.exists():
            header = [
                "---",
                f"topic: {topic}",
                "type: topic-index",
                f"tags: [{topic}]",
                "---",
                "",
                f"# {topic}",
                "",
                "## 文献索引",
                "",
            ]
            filepath.write_text("\n".join(header), encoding="utf-8")

        with open(filepath, "a", encoding="utf-8") as f:
            f.write("\n".join(new_entries) + "\n")


def main():
    daily_file = ROOT / "analysis_daily.json"
    weekly_file = ROOT / "analysis_weekly.json"

    today = datetime.now(TZ).strftime("%Y-%m-%d")

    # ---- Daily mode ----
    if daily_file.exists():
        print("[obsidian:daily] 生成每日文献笔记...")
        with open(daily_file, encoding="utf-8") as f:
            analysis = json.load(f)

        papers = analysis.get("papers", [])
        note_paths = []
        for p in papers:
            path = write_paper_note(p, today)
            if path:
                note_paths.append(path)

        print(f"  生成 {len(note_paths)} 篇独立笔记")

        if note_paths:
            write_daily_moc(today, papers, note_paths)
            update_topic_index(papers)
            print(f"  每日索引: {INBOX / f'{today}.md'}")

    # ---- Weekly mode ----
    if weekly_file.exists():
        print("[obsidian:weekly] 生成周度综述...")
        with open(weekly_file, encoding="utf-8") as f:
            result = json.load(f)

        meta = result.get("_meta", {})
        gen_time = meta.get("generated_at", today)
        end_date = gen_time[:10] if gen_time else today

        # 计算起始日期（7 天前）
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=6)
        start_date = start_dt.strftime("%Y-%m-%d")

        wp = write_weekly_note(result, start_date, end_date)
        print(f"  周报: {wp}")

    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
