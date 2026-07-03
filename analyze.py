#!/usr/bin/env python3
"""LLM 文献分析引擎 — 支持 daily（逐篇深度提炼）和 weekly（周度综述）两种模式."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "scraped_papers.json"
TZ = timezone(timedelta(hours=8))

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

BATCH_SIZE = 8  # 每批发给 LLM 的论文数


def load_papers() -> list[dict]:
    with open(INPUT, encoding="utf-8") as f:
        return json.load(f)["papers"]


def priority_key(p: dict) -> int:
    """按期刊影响力和摘要质量排序."""
    tier1 = {"N Engl J Med", "Lancet", "JAMA", "BMJ", "Nat Med"}
    source = p.get("source", "")
    score = 0
    for t in tier1:
        if t.lower() in source.lower():
            score += 30
            break
    abstract = p.get("abstract", "")
    if len(abstract) > 300:
        score += 15
    elif len(abstract) > 100:
        score += 8
    title = p.get("title", "").lower()
    for kw in ["nutrition", "diet", "microbiome", "microbiota", "obesity",
               "prevention", "trial", "cohort", "meta-analysis", "rct",
               "metabolic", "inflammation", "gut", "food", "nutrient"]:
        if kw in title:
            score += 2
    return score


def call_llm(system: str, user: str, json_mode: bool = True) -> dict | None:
    """调用 DeepSeek API."""
    import urllib.request

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            return json.loads(content) if json_mode else {"text": content}
    except Exception as e:
        print(f"  [ERROR] API 调用失败: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# Daily mode: per-paper deep analysis
# ═══════════════════════════════════════════════════════════════

DAILY_SYSTEM = """你是一位预防医学与营养学领域的研究方法学家。你的任务是对每篇论文做深度结构化提炼。

对于每篇论文，输出以下字段：
- title_cn: 中文标题（准确概括研究内容）
- background: 研究背景（1-2句，说明为什么做这个研究）
- methods: 方法简述（研究设计、样本量、干预/暴露、主要结局）
- findings: 核心发现（2-3句，包含关键数据）
- significance: 学术/临床意义（1-2句）
- limitation: 主要局限性（1句）
- relevance: 与你关注领域的关联（预防医学/营养流行病学/肠道菌群/慢性病预防，1句；如不相关则写"不直接相关"）
- relevance_score: 相关性评分（1-10整数，10=高度相关，1=几乎不相关）。评分标准：直接研究营养/膳食/菌群对疾病预防/代谢的影响→8-10分；涉及营养但非核心→5-7分；仅间接相关或主题距离较远→1-4分

严格按照 JSON 格式输出，relevance_score 必须是整数。"""


def build_daily_batch(papers: list[dict]) -> str:
    lines = ["请逐篇分析以下论文，返回 JSON 数组：\n"]
    for i, p in enumerate(papers, 1):
        title = p.get("title", "")
        source = p.get("source", "")
        abstract = p.get("abstract", "")[:600]
        pmid = p.get("pmid", "")
        url = p.get("url", "")
        date = p.get("date", "")

        lines.append(f"## 论文 {i}")
        lines.append(f"标题: {title}")
        lines.append(f"来源: {source}")
        if pmid:
            lines.append(f"PMID: {pmid}")
        if url:
            lines.append(f"链接: {url}")
        if date:
            lines.append(f"日期: {date}")
        if abstract:
            lines.append(f"摘要: {abstract}")
        lines.append("")
    lines.append('输出格式: {"papers": [{"index": 1, "title_cn": "...", ...}, ...]}')
    return "\n".join(lines)


def analyze_daily(papers: list[dict]) -> dict:
    papers_sorted = sorted(papers, key=priority_key, reverse=True)
    top = papers_sorted[:40]  # 每天最多分析 40 篇
    if not top:
        return {"papers": [], "_meta": {"analyzed": 0}}

    results: list[dict] = []
    batches = [top[i:i + BATCH_SIZE] for i in range(0, len(top), BATCH_SIZE)]
    _PASSTHROUGH = ["pmid", "url", "source", "date", "authors",
                   "volume", "issue", "pages", "issn", "essn",
                   "journal_full", "pub_types", "elocationid", "epubdate"]

    for bi, batch in enumerate(batches):
        print(f"  [{bi + 1}/{len(batches)}] 分析 {len(batch)} 篇...", end=" ", flush=True)
        prompt = build_daily_batch(batch)
        resp = call_llm(DAILY_SYSTEM, prompt)
        if resp and "papers" in resp:
            batch_results = resp["papers"]
            # 补上原始数据（包括论文元数据）
            for br in batch_results:
                idx = br.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    br["pmid"] = batch[idx].get("pmid", "")
                    br["url"] = batch[idx].get("url", "")
                    br["source"] = batch[idx].get("source", "")
                    br["original_title"] = batch[idx].get("title", "")
                    br["date"] = batch[idx].get("date", "")
                    for f in _PASSTHROUGH:
                        val = batch[idx].get(f)
                        if val:  # 只覆盖非空值，保留 LLM 可能已填的字段
                            br[f] = val
            results.extend(batch_results)
            print(f"OK ({len(batch_results)}篇)")
        else:
            print("FAIL")
            # 回退：保留原始数据
            for j, p in enumerate(batch):
                fb = {
                    "index": bi * BATCH_SIZE + j + 1,
                    "title_cn": p.get("title", ""),
                    "background": "",
                    "methods": "",
                    "findings": p.get("abstract", "")[:300],
                    "significance": "",
                    "limitation": "",
                    "relevance": "",
                    "relevance_score": 5,
                    "pmid": p.get("pmid", ""),
                    "url": p.get("url", ""),
                    "source": p.get("source", ""),
                    "original_title": p.get("title", ""),
                    "date": p.get("date", ""),
                }
                for f in _PASSTHROUGH:
                    val = p.get(f)
                    if val:
                        fb[f] = val
                results.append(fb)

        if bi < len(batches) - 1:
            time.sleep(0.5)

    return {
        "papers": results,
        "_meta": {
            "total_papers": len(papers),
            "analyzed": len(results),
            "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
            "model": MODEL,
            "mode": "daily",
        },
    }


# ═══════════════════════════════════════════════════════════════
# Weekly mode: synthesis across papers
# ═══════════════════════════════════════════════════════════════

WEEKLY_SYSTEM = """你是一位预防医学与营养学领域的资深研究员。请基于本周所有论文的分析结果，撰写一份周度综述。

输出 JSON：
{
  "headline": "本周最重要的发现（一句话）",
  "sections": [
    {
      "theme": "主题名",
      "summary": "该主题本周的研究进展概述（3-5句）",
      "key_papers": [{"title_cn": "...", "takeaway": "一句话要点"}]
    }
  ],
  "trends": ["趋势判断1", "趋势判断2"],
  "research_gaps": ["值得关注的研究空白1"],
  "spotlight": "本周最值得精读的一篇论文及理由"
}"""


def build_weekly_prompt(analyzed_papers: list[dict], raw_papers: list[dict]) -> str:
    lines = ["## 本周已分析论文摘要\n"]
    for p in analyzed_papers[:60]:
        lines.append(f"- **{p.get('title_cn', '?')}** [{p.get('source', '')}]")
        findings = p.get("findings", "")
        if findings:
            lines.append(f"  发现: {findings[:200]}")
        sig = p.get("significance", "")
        if sig:
            lines.append(f"  意义: {sig[:150]}")
        lines.append("")
    lines.append(f"\n共 {len(raw_papers)} 篇文献，其中 {len(analyzed_papers)} 篇已深度分析。")
    lines.append("请基于以上信息撰写周度综述。")
    return "\n".join(lines)


def analyze_weekly(analyzed_papers: list[dict], raw_papers: list[dict]) -> dict:
    prompt = build_weekly_prompt(analyzed_papers, raw_papers)
    print(f"  Prompt 长度: {len(prompt)} 字符")
    resp = call_llm(WEEKLY_SYSTEM, prompt, json_mode=False)
    # weekly uses text output, parse it manually if needed
    if resp:
        text = resp.get("text", "")
        # Try to extract JSON from text
        try:
            import re
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                result = json.loads(m.group())
            else:
                result = {"headline": text[:200], "sections": [], "trends": [], "research_gaps": [], "spotlight": ""}
        except json.JSONDecodeError:
            result = {"headline": text[:200], "sections": [], "trends": [], "research_gaps": [], "spotlight": ""}
    else:
        result = {"headline": "", "sections": [], "trends": [], "research_gaps": [], "spotlight": ""}

    result["_meta"] = {
        "total_papers": len(raw_papers),
        "analyzed_papers": len(analyzed_papers),
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "model": MODEL,
        "mode": "weekly",
    }
    return result


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()

    if not API_KEY:
        print("[ERROR] DEEPSEEK_API_KEY 未设置")
        return 1

    if not INPUT.exists():
        print(f"[ERROR] {INPUT} 不存在")
        return 1

    papers = load_papers()
    print(f"[analyze:{args.mode}] {len(papers)} 篇论文")

    if args.mode == "daily":
        output_file = ROOT / "analysis_daily.json"
        result = analyze_daily(papers)
    else:
        # 尝试加载 daily analysis 作为输入
        daily_file = ROOT / "analysis_daily.json"
        analyzed = []
        if daily_file.exists():
            with open(daily_file, encoding="utf-8") as f:
                analyzed = json.load(f).get("papers", [])
        output_file = ROOT / "analysis_weekly.json"
        result = analyze_weekly(analyzed, papers)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    papers_count = len(result.get("papers", []))
    sections_count = len(result.get("sections", []))
    print(f"  输出: {output_file} ({papers_count or sections_count} 条目)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
