#!/usr/bin/env python3
"""LLM 中文分析引擎 — 将英文论文摘要提炼为中文分析报告."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "scraped_papers.json"
OUTPUT = ROOT / "analysis.json"
TZ = timezone(timedelta(hours=8))

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def load_papers() -> list[dict]:
    with open(INPUT, encoding="utf-8") as f:
        return json.load(f)["papers"]


def priority_key(p: dict) -> int:
    """粗略优先级排序."""
    tier1 = {"N Engl J Med", "Lancet", "JAMA", "BMJ", "Nat Med"}
    source = p.get("source", "")
    score = 0
    for t in tier1:
        if t.lower() in source.lower():
            score += 20
            break
    abstract = p.get("abstract", "")
    if len(abstract) > 200:
        score += 10
    if any(kw in p.get("title", "").lower() for kw in
           ["nutrition", "diet", "microbiome", "obesity", "prevention",
            "trial", "cohort", "meta-analysis"]):
        score += 5
    return score


def build_prompt(papers: list[dict]) -> str:
    """构建 LLM prompt."""
    lines = [
        "你是一位预防医学与营养学领域的资深研究员。请根据以下最新论文信息，用中文撰写一份文献周报分析。",
        "",
        "## 要求",
        "1. 将论文按主题聚类（如：肥胖与代谢、肠道菌群、心血管预防、营养流行病学、公共卫生等）",
        "2. 每个主题下列出最重要的 2-4 篇论文",
        "3. 每条包含：中文标题概括、研究类型、一句话核心发现、为什么重要",
        "4. 在末尾给出「本周趋势判断」（2-3 条）",
        "5. 输出严格的 JSON 格式，不要 markdown 标记",
        "",
        "## JSON Schema",
        "{",
        '  "sections": [',
        '    {',
        '      "theme": "主题名称（中文）",',
        '      "papers": [',
        '        {',
        '          "title_cn": "中文标题概括",',
        '          "study_type": "RCT / Meta / Cohort / Review / ...",',
        '          "finding": "一句话核心发现",',
        '          "significance": "为什么重要（1-2句）"',
        "        }",
        "      ]",
        "    }",
        "  ],",
        '  "trends": ["趋势1", "趋势2", "趋势3"],',
        '  "key_takeaway": "本周最重要的一件事（1-2句）"',
        "}",
        "",
        "## 待分析论文",
        "",
    ]

    for i, p in enumerate(papers, 1):
        title = p.get("title", "N/A")
        source = p.get("source", "Unknown")
        abstract = p.get("abstract", "")[:500]
        pmid = p.get("pmid", "")
        study_type = _guess_type(title, abstract)

        lines.append(f"### {i}. {title}")
        lines.append(f"来源: {source} | 可能类型: {study_type}")
        if pmid:
            lines.append(f"PMID: {pmid}")
        if abstract:
            lines.append(f"摘要: {abstract}")
        lines.append("")

    return "\n".join(lines)


def _guess_type(title: str, abstract: str) -> str:
    combined = (title + " " + abstract).lower()
    if "meta-analysis" in combined or "meta analysis" in combined:
        return "Meta-Analysis"
    if "systematic review" in combined:
        return "Systematic Review"
    if "randomized" in combined or "rct" in combined:
        return "RCT"
    if "cohort" in combined or "prospective" in combined:
        return "Cohort Study"
    if "trial" in combined:
        return "Clinical Trial"
    if "review" in combined:
        return "Review"
    if "cross-sectional" in combined:
        return "Cross-Sectional"
    return "Research Article"


def call_deepseek(prompt: str) -> dict | None:
    """调用 DeepSeek API (OpenAI 兼容接口)."""
    import urllib.request

    if not DEEPSEEK_API_KEY:
        print("[ERROR] DEEPSEEK_API_KEY 未设置")
        return None

    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一位预防医学与营养学研究员。只输出 JSON，不要额外文本。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        print(f"[ERROR] DeepSeek API 调用失败: {e}")
        return None


def main():
    if not INPUT.exists():
        print(f"[ERROR] {INPUT} 不存在，请先运行 scraper.py")
        return 1

    if not DEEPSEEK_API_KEY:
        print("[ERROR] 请设置环境变量 DEEPSEEK_API_KEY")
        return 1

    papers = load_papers()
    print(f"[1/3] 加载 {len(papers)} 篇论文")

    # 按优先级排序，取 top 50 发给 LLM
    papers.sort(key=priority_key, reverse=True)
    top_n = min(50, len(papers))
    top = papers[:top_n]
    print(f"[2/3] 发送 top {top_n} 篇到 DeepSeek 分析...")

    prompt = build_prompt(top)
    print(f"  Prompt 长度: {len(prompt)} 字符")
    analysis = call_deepseek(prompt)

    if not analysis:
        return 1

    # 注入来源信息（PMID 等）
    analysis["_meta"] = {
        "total_papers": len(papers),
        "analyzed_papers": top_n,
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "model": DEEPSEEK_MODEL,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"[3/3] 分析结果保存到 {OUTPUT}")

    # 预览
    sections = analysis.get("sections", [])
    print(f"\n  主题数: {len(sections)}")
    for s in sections:
        print(f"    - {s.get('theme', '?')}: {len(s.get('papers', []))} 篇")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
