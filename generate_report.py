#!/usr/bin/env python3
"""将 scraped_papers.json 转换为可推送的 Markdown 报告."""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "scraped_papers.json"
OUTPUT = ROOT / "report.md"

# 目标期刊影响因子排序（粗略分层，用于优先级）
TIER_1 = {"N Engl J Med", "Lancet", "JAMA", "BMJ", "Nat Med"}
TIER_2 = {"Gut Microbes", "Microbiome", "Am J Clin Nutr", "J Nutr", "Nutrients",
          "Int J Obes", "Obes Rev", "Am J Epidemiol", "Int J Epidemiol",
          "Am J Prev Med", "Prev Med", "Public Health Nutr", "Eur J Clin Nutr",
          "Epidemiology", "PLOS Medicine"}

TZ = timezone(timedelta(hours=8))


def priority_score(paper: dict) -> int:
    """根据期刊层级和研究类型计算优先级."""
    score = 0
    source = paper.get("source", "")
    title = paper.get("title", "").lower()
    abstract = paper.get("abstract", "").lower()

    for t in TIER_1:
        if t.lower() in source.lower():
            score += 30
            break
    else:
        for t in TIER_2:
            if t.lower() in source.lower():
                score += 20
                break

    # 研究类型加分
    combined = title + " " + abstract
    if any(kw in combined for kw in ["meta-analysis", "meta analysis"]):
        score += 15
    elif "systematic review" in combined:
        score += 12
    elif "randomized" in combined or "rct" in combined:
        score += 10
    elif "cohort" in combined or "prospective" in combined:
        score += 8
    elif "trial" in combined:
        score += 6
    elif "review" in combined:
        score += 4

    # 关键词匹配
    keywords = [
        "nutrition", "diet", "microbiome", "microbiota", "obesity",
        "prevention", "public health", "epidemiology", "food",
        "nutrient", "metabolic", "inflammation", "aging",
    ]
    for kw in keywords:
        if kw in title:
            score += 2

    # 如有真正摘要（非仅期刊名）加分
    if len(abstract) > 100:
        score += 5

    return score


def generate_report() -> str:
    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)

    papers = data["papers"]
    meta = data["meta"]
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    # 排序
    papers.sort(key=priority_score, reverse=True)

    # 筛选高度相关 + 有摘要的（至少摘要长度合理）
    top = [p for p in papers if priority_score(p) >= 15][:12]
    if len(top) < 5:
        top = papers[:10]

    lines = []
    lines.append(f"# 预防医学与营养学文献周报")
    lines.append(f"**生成日期：{today}** | 覆盖范围：过去 7 天 | 共 {meta['total_papers']} 篇")
    lines.append("")
    lines.append(f"> 来源：PubMed({meta['sources']['pubmed']}) · RSS({meta['sources']['rss']}) · "
                 f"预印本({meta['sources']['preprints']}) · 临床试验({meta['sources']['trials']})")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 本周重点关注")
    lines.append("")

    for i, p in enumerate(top, 1):
        title = p["title"].strip()
        source = p.get("source", "Unknown")
        url = p.get("url", "")
        abstract = p.get("abstract", "")
        pmid = p.get("pmid", "")

        # 清理来源显示
        source_clean = source.replace(" → ", " / ")

        lines.append(f"### {i}. {title}")
        lines.append(f"**来源：**{source_clean}")
        if pmid:
            lines.append(f"**PubMed ID：**[{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
        if url:
            lines.append(f"**链接：**[DOI]({url})")

        if abstract and len(abstract) > 80:
            lines.append(f"**摘要：**{abstract[:400]}{'...' if len(abstract) > 400 else ''}")

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 完整文献列表")
    lines.append("")
    lines.append("| # | 标题 | 来源 |")
    lines.append("|---|------|------|")
    for i, p in enumerate(papers, 1):
        title = p["title"].strip()[:80]
        source = p.get("source", "").replace(" → ", " / ")[:40]
        url = p.get("url", "")
        if url:
            title_md = f"[{title}]({url})"
        else:
            title_md = title
        lines.append(f"| {i} | {title_md} | {source} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*自动生成于 {today} · 预防医学与营养学文献推送系统*")
    lines.append(f"*下次推送：{next_weekday()}*")

    return "\n".join(lines)


def next_weekday() -> str:
    """下周一日期."""
    today = datetime.now(TZ).date()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")


def save_report(report: str) -> Path:
    OUTPUT.write_text(report, encoding="utf-8")
    return OUTPUT


def save_to_obsidian(report: str) -> Path:
    vault = Path("G:/obsidian/Inbox")
    if not vault.exists():
        print(f"[WARN] Obsidian vault not found: {vault}")
        return None
    today = datetime.now(TZ).strftime("%Y%m%d")
    path = vault / f"文献周报-{today}.md"
    path.write_text(report, encoding="utf-8")
    return path


def main():
    print("[1/3] 生成报告...")
    report = generate_report()
    out = save_report(report)
    print(f"  [OK] 报告已保存: {out} ({len(report)} 字符)")

    print("[2/3] 保存到 Obsidian...")
    obs_path = save_to_obsidian(report)
    if obs_path:
        print(f"  [OK] Obsidian: {obs_path}")

    print("[3/3] 完成")
    return report


if __name__ == "__main__":
    main()
