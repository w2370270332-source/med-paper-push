#!/usr/bin/env python3
"""报告生成器 — 支持 daily（日报）和 weekly（周报）两种模式."""

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_daily(analysis: dict, papers_data: dict) -> str:
    """生成日报：逐篇深度提炼."""
    papers = analysis.get("papers", [])
    meta = papers_data.get("meta", {})
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now(TZ).weekday()]

    lines = [
        f"# 预防医学与营养学文献日报",
        f"",
        f"**{today}（{weekday}）** | 检索到 {meta.get('total_papers', len(papers))} 篇 | "
        f"深度分析 {len(papers)} 篇",
        f"",
        f"> PubMed({meta.get('sources', {}).get('pubmed', '?')}) · "
        f"RSS({meta.get('sources', {}).get('rss', '?')}) · "
        f"预印本({meta.get('sources', {}).get('preprints', '?')}) · "
        f"临床试验({meta.get('sources', {}).get('trials', '?')})",
        f"",
        f"---",
        f"",
    ]

    if not papers:
        lines.append("今日无新文献。")
        return "\n".join(lines)

    # 按来源分组
    for i, p in enumerate(papers, 1):
        title_cn = p.get("title_cn", "") or p.get("original_title", "")
        original_title = p.get("original_title", "")
        source = p.get("source", "")
        pmid = p.get("pmid", "")
        url = p.get("url", "")
        background = p.get("background", "")
        methods = p.get("methods", "")
        findings = p.get("findings", "")
        significance = p.get("significance", "")
        limitation = p.get("limitation", "")
        relevance = p.get("relevance", "")

        lines.append(f"## {i}. {title_cn}")
        lines.append("")

        if original_title and original_title != title_cn:
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

    lines.append(f"*日报生成于 {today} · 模型：{analysis.get('_meta', {}).get('model', 'LLM')}*")
    return "\n".join(lines)


def generate_weekly(result: dict, papers_data: dict) -> str:
    """生成周报：综述+趋势+精读推荐."""
    meta = papers_data.get("meta", {})
    am = result.get("_meta", {})
    gen_time = am.get("generated_at", datetime.now(TZ).strftime("%Y-%m-%d"))
    end_date = gen_time[:10] if gen_time else datetime.now(TZ).strftime("%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=6)
    start_date = start_dt.strftime("%Y-%m-%d")

    headline = result.get("headline", "")
    sections = result.get("sections", [])
    trends = result.get("trends", [])
    gaps = result.get("research_gaps", [])
    spotlight = result.get("spotlight", "")

    lines = [
        f"# 预防医学与营养学文献周报",
        f"",
        f"**{start_date} → {end_date}** | 共检索 {am.get('total_papers', meta.get('total_papers', '?'))} 篇 | "
        f"深度分析 {am.get('analyzed_papers', '?')} 篇",
        f"",
    ]

    if headline:
        lines.append(f"> **📌 {headline}**")
        lines.append("")

    lines.append("---")
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
        lines.append("---")
        lines.append("")
        lines.append("## 趋势判断")
        lines.append("")
        for i, t in enumerate(trends, 1):
            lines.append(f"{i}. {t}")
        lines.append("")

    if gaps:
        lines.append("## 值得关注的研究空白")
        lines.append("")
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")

    if spotlight:
        lines.append("---")
        lines.append("")
        lines.append("## 本周精读推荐")
        lines.append("")
        lines.append(spotlight)
        lines.append("")

    lines.append("---")
    lines.append(f"*周报生成于 {gen_time} · 模型：{am.get('model', 'LLM')}*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()

    papers_file = ROOT / "scraped_papers.json"

    if not papers_file.exists():
        print(f"[ERROR] {papers_file} 不存在")
        return 1

    papers_data = load_json(papers_file)

    if args.mode == "daily":
        analysis_file = ROOT / "analysis_daily.json"
        output_file = ROOT / "report_daily.md"
        if not analysis_file.exists():
            print(f"[ERROR] {analysis_file} 不存在，请先运行 analyze.py --mode daily")
            return 1
        analysis = load_json(analysis_file)
        report = generate_daily(analysis, papers_data)
    else:
        analysis_file = ROOT / "analysis_weekly.json"
        output_file = ROOT / "report_weekly.md"
        if not analysis_file.exists():
            print(f"[ERROR] {analysis_file} 不存在，请先运行 analyze.py --mode weekly")
            return 1
        result = load_json(analysis_file)
        report = generate_weekly(result, papers_data)

    output_file.write_text(report, encoding="utf-8")
    print(f"[report:{args.mode}] {output_file} ({len(report)} 字符)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
