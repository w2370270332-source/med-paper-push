#!/usr/bin/env python3
"""将 LLM 分析结果 + 文献列表转换为 Markdown 推送报告."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAPERS_FILE = ROOT / "scraped_papers.json"
ANALYSIS_FILE = ROOT / "analysis.json"
OUTPUT = ROOT / "report.md"
TZ = timezone(timedelta(hours=8))


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_report(papers_data: dict, analysis: dict | None) -> str:
    papers = papers_data["papers"]
    meta = papers_data["meta"]
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now(TZ).weekday()]

    lines = []
    lines.append(f"# 预防医学与营养学文献周报")
    lines.append(f"")
    lines.append(f"**{today}（{weekday}）** | 覆盖：过去 7 天 | 共检索 **{meta['total_papers']}** 篇文献")
    lines.append("")
    lines.append(f"> PubMed({meta['sources']['pubmed']}) · RSS({meta['sources']['rss']}) · "
                 f"预印本({meta['sources']['preprints']}) · 临床试验({meta['sources']['trials']})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---- LLM 分析部分 ----
    if analysis and analysis.get("sections"):
        # Key takeaway
        if analysis.get("key_takeaway"):
            lines.append(f"> **📌 {analysis['key_takeaway']}**")
            lines.append("")

        for section in analysis["sections"]:
            theme = section.get("theme", "其他")
            sec_papers = section.get("papers", [])
            if not sec_papers:
                continue

            lines.append(f"## {theme}")
            lines.append("")

            for j, p in enumerate(sec_papers, 1):
                title_cn = p.get("title_cn", "未知标题")
                study_type = p.get("study_type", "")
                finding = p.get("finding", "")
                significance = p.get("significance", "")

                type_badge = f" **({study_type})**" if study_type else ""
                lines.append(f"### {j}. {title_cn}{type_badge}")
                lines.append("")

                if finding:
                    lines.append(f"**要点：**{finding}")
                    lines.append("")
                if significance:
                    lines.append(f"**临床意义：**{significance}")
                    lines.append("")

            lines.append("")

        # 趋势判断
        trends = analysis.get("trends", [])
        if trends:
            lines.append("---")
            lines.append("")
            lines.append("## 本周趋势判断")
            lines.append("")
            for i, t in enumerate(trends, 1):
                lines.append(f"{i}. {t}")
            lines.append("")

    else:
        # 无 LLM 分析时回退到简单列表
        lines.append("## 本周重点论文")
        lines.append("")
        papers_sorted = sorted(papers, key=lambda p: len(p.get("abstract", "")), reverse=True)
        for i, p in enumerate(papers_sorted[:15], 1):
            title = p.get("title", "").strip()
            source = p.get("source", "Unknown")
            url = p.get("url", "")
            abstract = p.get("abstract", "")[:300]
            pmid = p.get("pmid", "")

            lines.append(f"### {i}. {title}")
            lines.append(f"**来源：**{source}")
            if pmid:
                lines.append(f"**PMID：**[{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
            if url:
                lines.append(f"**链接：**[DOI]({url})")
            if abstract:
                lines.append(f"**摘要：**{abstract}{'...' if len(abstract) >= 300 else ''}")
            lines.append("")

    # ---- 完整文献列表 ----
    lines.append("---")
    lines.append("")
    lines.append("## 完整文献列表")
    lines.append("")
    lines.append("| # | 标题 | 来源 |")
    lines.append("|---|------|------|")
    for i, p in enumerate(papers, 1):
        title = p.get("title", "").strip()[:80]
        source = p.get("source", "").replace(" → ", " / ")[:40]
        url = p.get("url", "")
        title_md = f"[{title}]({url})" if url else title
        lines.append(f"| {i} | {title_md} | {source} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    if analysis and analysis.get("_meta"):
        am = analysis["_meta"]
        lines.append(f"*LLM 分析：{am['analyzed_papers']}/{am['total_papers']} 篇 · "
                     f"模型：{am['model']} · 生成时间：{am['generated_at']}*")
    else:
        lines.append(f"*自动生成于 {today} · 预防医学与营养学文献推送系统*")
    lines.append(f"*下次推送：{next_monday()}*")

    return "\n".join(lines)


def next_monday() -> str:
    today = datetime.now(TZ).date()
    days = (7 - today.weekday()) % 7 or 7
    return (today + timedelta(days=days)).strftime("%Y-%m-%d")


def main():
    if not PAPERS_FILE.exists():
        print(f"[ERROR] {PAPERS_FILE} 不存在，请先运行 scraper.py")
        return 1

    papers_data = load_json(PAPERS_FILE)
    analysis = None
    if ANALYSIS_FILE.exists():
        analysis = load_json(ANALYSIS_FILE)
        print("[1/3] 加载 LLM 分析结果")
    else:
        print("[1/3] 未找到分析结果，回退到简单列表模式")

    print("[2/3] 生成报告...")
    report = generate_report(papers_data, analysis)
    OUTPUT.write_text(report, encoding="utf-8")
    print(f"  [OK] 报告已保存: {OUTPUT} ({len(report)} 字符)")

    print("[3/3] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
