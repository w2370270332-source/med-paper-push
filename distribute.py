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
    "咖啡风味化学与品质": ["咖啡", "coffee", "风味", "flavor", "aroma", "香气", "杯测", "cupping",
        "咖啡豆", "生豆", "烘焙", "roasting", "品种", "variety", "产地", "origin", "terroir",
        "加工方式", "processing", "阿拉比卡", "arabica", "罗布斯塔", "robusta",
        "绿原酸", "chlorogenic", "葫芦巴碱", "trigonelline", "咖啡因", "caffeine",
        "吡嗪", "pyrazine", "呋喃", "furan", "硫化物", "sulfide",
        "HS-SPME", "GC-MS", "GC×GC", "代谢组学", "metabolomics", "感官", "sensory",
        "分子感官", "molecular sensory", "气味活性", "OAV", "AEDA",
        "美拉德", "Maillard", "焦糖化", "caramelization",
        "食品化学", "food chemistry", "风味化学", "flavor chemistry",
        "香气重组", "aroma recombination", "香气缺失", "omission"],
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


# ═══════════════════════════════════════════════════════════════
# Deep Analysis (Plan A — on-demand, only for pushed papers)
# ═══════════════════════════════════════════════════════════════

DEEP_SYSTEM = """你是一位预防医学与营养学领域的研究方法学家。对这篇论文进行深度结构化提炼。

输出以下字段（每个字段必须详尽，禁止只写一两句话敷衍）：
- title_cn: 中文标题（准确概括研究内容）
- background: 研究背景（3-5句：领域现状→知识缺口→研究假设）
- objective: 研究目的（1句，明确具体）
- design: 研究设计（设计类型+盲法+随访时长+注册号）
- population: 研究对象（样本量+来源+入排标准+基线特征）
- intervention: 干预/暴露详情（剂量/频率/对照/依从性）
- outcomes: 结局指标（主要结局+次要结局+检测方法）
- findings: 核心发现（5-8句，必须包含效应量+置信区间+p值+亚组分析+敏感性分析，无数据的字段标注"未报告"）
- mechanism: 生物学机制（2-3句，解释观察到效应的生物学通路）
- comparison: 与同类研究对比（2-3句，与已有证据的一致/矛盾之处）
- significance: 学术/临床意义（2-3句，对领域/指南/实践的具体影响）
- limitation: 局限性（2-3个主要局限：偏倚风险/混杂控制/外推性/样本代表性）
- relevance: 与预防医学/营养流行病学/肠道菌群/慢性病预防的关联（1-2句）
- relevance_score: 相关性评分（1-10整数）

严格按照 JSON 格式输出，relevance_score 必须是整数。"""

# 咖啡风味化学深度分析提示词（针对匹配到咖啡领域的论文进行二次深度分析）
COFFEE_DEEP_SYSTEM = """你是一位咖啡风味化学与食品代谢组学领域的专家。这篇论文与咖啡研究高度相关，请进行专业深度的结构化提炼。

输出以下字段（详尽程度要达到学科同行能直接引用）：
- title_cn: 中文标题
- coffee_context: 该研究在咖啡科学中的定位（3-5句：与咖啡品种/产地/加工/风味品质的关系，填补了什么空白）
- coffee_species: 研究的咖啡品种/种（Arabica/Robusta/Liberica/Stenophylla 等，未提及标注"未报告"）
- sample_info: 样品信息（产地/海拔/加工方式/烘焙程度/样品量，越详细越好）
- analytical_methods: 分析方法（GC-MS/LC-MS/GC×GC-TOFMS/NIR/感官杯测等，列出具体仪器和条件）
- key_compounds: 关键化合物发现（列出具体化合物名称+浓度范围+统计学显著性+风味描述）
- sensory_link: 化学-感官关联（化合物如何影响风味/香气/口感，OAV值，感官评分关联性）
- processing_impact: 加工/烘焙影响（加工方式或烘焙程度对化合物的影响，如有）
- mechanism: 形成机制（关键化合物的生物合成或热反应形成途径）
- comparison: 与已有咖啡文献的对比（2-3句，与咖啡风味化学领域已有共识的一致/矛盾）
- practical_implication: 实践意义（对咖啡品种选育/产地鉴别/品质分级/加工优化的指导价值，2-3句）
- limitation: 局限性（2-3个，从咖啡研究角度）
- relevance_score: 相关性评分（1-10整数）

严格按照 JSON 格式输出。"""

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 咖啡论文关键词（用于判断是否需要特化深度分析）
COFFEE_KEYWORDS = [
    "coffee", "arabica", "robusta", "咖啡", "roasting", "烘焙",
    "barista", "cappuccino", "latte", "caffeine", "咖啡因",
    "chlorogenic", "绿原酸", "trigonelline", "葫芦巴碱",
    "coffee flavor", "coffee aroma", "coffee metabolomics",
]


def _call_llm(system: str, user: str) -> dict | None:
    """调用 DeepSeek API (JSON mode)."""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
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
            return json.loads(content)
    except Exception as e:
        print(f"  [LLM ERROR] {e}")
        return None


def deep_analyze_papers(papers: list[dict]) -> list[dict]:
    """对论文进行深度分析（方案A），咖啡论文使用特化深度分析。结果回存 paper_pool."""
    if not API_KEY:
        print("  [deep] DEEPSEEK_API_KEY 未设置，使用浅层分析")
        return papers

    # 分离咖啡论文和普通论文
    coffee_papers = [p for p in papers if _is_coffee_paper(p)]
    normal_papers = [p for p in papers if p not in coffee_papers]

    enriched = []
    if normal_papers:
        enriched.extend(_deep_analyze_normal(normal_papers))
    if coffee_papers:
        enriched.extend(_deep_analyze_coffee(coffee_papers))
    return enriched


def _is_coffee_paper(p: dict) -> bool:
    """判断论文是否属于咖啡风味化学领域."""
    combined = " ".join([
        p.get("title_cn") or "", p.get("original_title") or "",
        p.get("title") or "", p.get("findings") or "",
        p.get("abstract") or "", p.get("source") or "",
    ]).lower()
    return any(kw.lower() in combined for kw in COFFEE_KEYWORDS)


def _deep_analyze_coffee(papers: list[dict]) -> list[dict]:
    """咖啡论文特化深度分析."""
    need_deep = _filter_needs_deep(papers)
    if not need_deep:
        return papers

    print(f"  [coffee-deep] {len(need_deep)} 篇咖啡论文需要特化深度分析...")
    BATCH = min(3, len(need_deep))

    for bi in range(0, len(need_deep), BATCH):
        batch = need_deep[bi:bi + BATCH]
        lines = ["请逐篇深度分析以下咖啡相关论文，返回 JSON 数组：\n"]
        for j, p in enumerate(batch, 1):
            title = (p.get("original_title") or p.get("title") or "")
            source = p.get("source", "")
            abstract = (p.get("findings") or p.get("abstract") or "")[:800]
            lines.append(f"## 论文 {j}")
            lines.append(f"标题: {title}")
            lines.append(f"来源: {source}")
            lines.append(f"摘要/初步发现: {abstract}")
            lines.append("")
        lines.append('输出格式: {"papers": [{"index": 1, "title_cn": "...", ...}, ...]}')

        total_batches = (len(need_deep) + BATCH - 1) // BATCH
        print(f"    [{bi // BATCH + 1}/{total_batches}] {len(batch)} 篇...", end=" ", flush=True)
        resp = _call_llm(COFFEE_DEEP_SYSTEM, "\n".join(lines))

        if resp and "papers" in resp:
            for item in resp["papers"]:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    original = batch[idx]
                    pid = original.get("id")
                    payload = {k: v for k, v in item.items()
                               if k in ["coffee_context", "coffee_species", "sample_info",
                                         "analytical_methods", "key_compounds", "sensory_link",
                                         "processing_impact", "mechanism", "comparison",
                                         "practical_implication", "limitation"]}
                    # 合并到 deep_analysis
                    existing = original.get("deep_analysis") or {}
                    if isinstance(existing, dict):
                        existing.update(payload)
                    else:
                        existing = payload
                    existing["_coffee_special"] = True  # 标记为咖啡特化分析
                    if pid:
                        _supa(f"paper_pool?id=eq.{pid}", "PATCH", {"deep_analysis": existing})
                    original["deep_analysis"] = existing
            print(f"OK")
        else:
            print("FAIL")
            # Fallback: use normal deep analysis
            for p in batch:
                p["deep_analysis"] = p.get("deep_analysis") or {}

        if bi + BATCH < len(need_deep):
            import time
            time.sleep(1)

    return papers


def _filter_needs_deep(papers: list[dict]) -> list[dict]:
    """筛选需要深度分析的论文（跳过已有完整深度分析的）."""
    need = []
    for p in papers:
        existing = p.get("deep_analysis")
        if isinstance(existing, dict) and existing.get("background"):
            continue
        if p.get("id"):
            need.append(p)
    return need


def _deep_analyze_normal(papers: list[dict]) -> list[dict]:
    """普通论文深度分析（原逻辑）."""
    need_deep = _filter_needs_deep(papers)
    if not need_deep:
        print(f"  [deep] {len(papers)} 篇均已有深度分析，跳过")
        return papers

    print(f"  [deep] {len(need_deep)} 篇需要深度分析...")
    BATCH = min(4, len(need_deep))

    for bi in range(0, len(need_deep), BATCH):
        batch = need_deep[bi:bi + BATCH]
        lines = ["请逐篇分析以下论文，返回 JSON 数组：\n"]
        for j, p in enumerate(batch, 1):
            title = (p.get("original_title") or p.get("title") or "")
            source = p.get("source", "")
            abstract = (p.get("findings") or p.get("abstract") or "")[:800]
            lines.append(f"## 论文 {j}")
            lines.append(f"标题: {title}")
            lines.append(f"来源: {source}")
            lines.append(f"摘要/初步发现: {abstract}")
            lines.append("")
        lines.append('输出格式: {"papers": [{"index": 1, "title_cn": "...", ...}, ...]}')

        print(f"    [{bi // BATCH + 1}/{ (len(need_deep) + BATCH - 1) // BATCH}] {len(batch)} 篇...", end=" ", flush=True)
        resp = _call_llm(DEEP_SYSTEM, "\n".join(lines))

        if resp and "papers" in resp:
            for item in resp["papers"]:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    original = batch[idx]
                    pid = original.get("id")
                    # 存回 paper_pool
                    payload = {
                        k: v for k, v in item.items()
                        if k in ["background", "objective", "design", "population",
                                  "intervention", "outcomes", "findings", "mechanism",
                                  "comparison", "significance", "limitation", "relevance"]
                    }
                    if pid:
                        _supa(f"paper_pool?id=eq.{pid}", "PATCH", {"deep_analysis": payload})
                    # 合并到原始 dict
                    original["deep_analysis"] = payload
                    enriched.append(original)
            print(f"OK")
        else:
            print("FAIL")
            enriched.extend(batch)

        if bi + BATCH < len(need_deep):
            import time
            time.sleep(1)

    return enriched


def _deep_field(p: dict, key: str) -> str:
    """优先从 deep_analysis 取字段，回退到顶级字段."""
    da = p.get("deep_analysis")
    if isinstance(da, dict):
        val = da.get(key, "")
        if val:
            return str(val)
    return (p.get(key) or "").strip()


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

        # 优先使用深度分析字段
        background = _deep_field(paper, "background")
        findings = _deep_field(paper, "findings")
        significance = _deep_field(paper, "significance")
        limitation = _deep_field(paper, "limitation")
        mechanism = _deep_field(paper, "mechanism")
        comparison = _deep_field(paper, "comparison")
        objective = _deep_field(paper, "objective")
        design = _deep_field(paper, "design")
        population = _deep_field(paper, "population")
        intervention = _deep_field(paper, "intervention")
        outcomes = _deep_field(paper, "outcomes")

        citation = source_clean or source_raw
        if volume:
            citation += f" {volume}"
            if issue:
                citation += f"({issue})"
            if pages:
                citation += f":{pages}"

        star_html = _stars(score)

        # 咖啡论文特殊标记
        is_coffee = bool(
            isinstance(paper.get("deep_analysis"), dict)
            and paper["deep_analysis"].get("_coffee_special")
        )
        coffee_badge = "☕ " if is_coffee else ""
        card_border = "2px solid #d4a574" if is_coffee else "1px solid #e2e6ec"
        card_bg = "#fffbf5" if is_coffee else "#fff"

        parts.append(f"""<div style="background:{card_bg};border-radius:10px;padding:24px;margin-bottom:16px;border:{card_border};">""")

        if is_coffee:
            parts.append('<div style="display:inline-block;background:linear-gradient(135deg,#d4a574,#8b6914);color:#fff;border-radius:20px;padding:2px 12px;font-size:11px;font-weight:700;margin-bottom:14px;">☕ 咖啡风味化学 · 重点标注</div>')

        parts.append(f"""
<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:14px;">
<span style="flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:#1a365d;color:#fff;border-radius:50%;font-size:13px;font-weight:700;">{idx}</span>
<div style="flex:1;min-width:0;">
<h2 style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1a365d;line-height:1.5;">{coffee_badge}{_h(title_cn)}</h2>
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

        # 研究方法（深度分析字段）
        methods_parts = []
        if design:
            methods_parts.append(f"<b>设计：</b>{_h(design)}")
        if population:
            methods_parts.append(f"<b>对象：</b>{_h(population)}")
        if intervention:
            methods_parts.append(f"<b>干预：</b>{_h(intervention)}")
        if outcomes:
            methods_parts.append(f"<b>结局：</b>{_h(outcomes)}")
        if methods_parts:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f8fafc;border-radius:6px;border:1px dashed #cbd5e1;"><div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:6px;">研究方法</div>{"<br>".join(methods_parts)}</div>\n')

        if background:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #4a90d9;"><div style="font-size:11px;font-weight:700;color:#4a90d9;margin-bottom:4px;">研究背景</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(background)}</p></div>\n')
        if findings:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #16a34a;"><div style="font-size:11px;font-weight:700;color:#16a34a;margin-bottom:4px;">核心发现</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(findings)}</p></div>\n')
        if mechanism:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f0f4ff;border-radius:6px;border-left:3px solid #7c3aed;"><div style="font-size:11px;font-weight:700;color:#7c3aed;margin-bottom:4px;">生物学机制</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(mechanism)}</p></div>\n')
        if comparison:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#fefce8;border-radius:6px;border-left:3px solid #ca8a04;"><div style="font-size:11px;font-weight:700;color:#ca8a04;margin-bottom:4px;">与同类研究对比</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(comparison)}</p></div>\n')
        if significance:
            parts.append(f'<div style="margin-bottom:12px;padding:12px 14px;background:#f7f8fa;border-radius:6px;border-left:3px solid #9333ea;"><div style="font-size:11px;font-weight:700;color:#9333ea;margin-bottom:4px;">研究意义</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(significance)}</p></div>\n')
        if limitation:
            parts.append(f'<div style="margin-bottom:0;padding:12px 14px;background:#fef2f2;border-radius:6px;border-left:3px solid #dc2626;"><div style="font-size:11px;font-weight:700;color:#dc2626;margin-bottom:4px;">局限性</div><p style="margin:0;font-size:14px;color:#2a3a4a;">{_h(limitation)}</p></div>\n')
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

        # 深度分析（仅对确定将被推送的论文）
        papers = deep_analyze_papers(papers)

        # 排除已推送给该用户的论文（防止同日及跨日重复）
        sent_history = _supa(
            f"push_history?select=paper_ids&user_id=eq.{user_id}"
            f"&pushed_at=gte.{(datetime.now(TZ) - timedelta(days=7)).isoformat()}"
        ) or []
        sent_ids: set[int] = set()
        for h in sent_history:
            ids = h.get("paper_ids") or []
            sent_ids.update(ids)
        if sent_ids:
            before = len(papers)
            papers = [p for p in papers if p.get("id") not in sent_ids]
            if len(papers) < before:
                print(f"  [dedup] 排除 {before - len(papers)} 篇已推送论文")

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

        # 深度分析（仅对确定将被推送的论文）
        papers = deep_analyze_papers(papers)

        # 排除已推送给该邮箱的论文
        sent_history = _supa(
            f"push_history?select=paper_ids&report_content=ilike.*{email}*"
            f"&pushed_at=gte.{(datetime.now(TZ) - timedelta(days=7)).isoformat()}"
        ) or []
        sent_ids: set[int] = set()
        for h in sent_history:
            ids = h.get("paper_ids") or []
            sent_ids.update(ids)
        if sent_ids:
            before = len(papers)
            papers = [p for p in papers if p.get("id") not in sent_ids]
            if len(papers) < before:
                print(f"  [dedup] 排除 {before - len(papers)} 篇已推送论文")

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
