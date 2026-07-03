#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-source literature fetcher using Scrapling.

覆盖:

四个渠道:
  1. PubMed E-utilities — 目标期刊最新论文（可靠骨干）
  2. RSS/Atom 源 — Nature/PLOS/BMC 等，可能比 PubMed 快数小时
  3. medRxiv/bioRxiv — 预印本直爬，PubMed 未收录
  4. ClinicalTrials.gov — 新注册试验

输出: scraped_papers.json（结构化数据，供报告生成器消费）
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from scrapling.fetchers import Fetcher, DynamicFetcher

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

OUTPUT = Path(__file__).parent / "scraped_papers.json"
DAYS_BACK = int(os.environ.get("SCRAPE_DAYS", "1"))  # 默认 1 天，可通过环境变量覆盖
MAX_PER_SOURCE = 30  # 每个源最多抓取条数

# ---------- 目标期刊（PubMed 检索用简称）----------
TARGET_JOURNALS: list[str] = [
    # 综合医学顶刊
    "N Engl J Med",
    "Lancet",
    "JAMA",
    "BMJ",
    "Nat Med",
    # 营养学
    "Am J Clin Nutr",
    "J Nutr",
    "Eur J Clin Nutr",
    "Public Health Nutr",
    "Nutrients",
    "Int J Obes",
    "Obes Rev",
    # 预防/流行病学
    "Prev Med",
    "Am J Prev Med",
    "Int J Epidemiol",
    "Am J Epidemiol",
    "Epidemiology",
    # 肠道菌群
    "Gut Microbes",
    "Microbiome",
]

# ---------- RSS/Atom 源（比 PubMed 快 0-1 天）----------
RSS_FEEDS: list[dict[str, str]] = [
    # Nature 系列 — RSS 稳定可用
    {"name": "Nature Medicine", "url": "https://www.nature.com/nm.rss"},
    {"name": "Eur J Clin Nutr", "url": "https://www.nature.com/ejcn.rss"},
    {"name": "Int J Obes", "url": "https://www.nature.com/ijo.rss"},
    # PLOS — Atom feed 可用
    {"name": "PLOS Medicine", "url": "https://journals.plos.org/plosmedicine/feed/atom"},
    {"name": "PLOS ONE", "url": "https://journals.plos.org/plosone/feed/atom"},
    # BMC
    {"name": "BMC Public Health", "url": "https://bmcpublichealth.biomedcentral.com/articles/most-recent/rss.xml"},
    {"name": "BMC Medicine", "url": "https://bmcmedicine.biomedcentral.com/articles/most-recent/rss.xml"},
    {"name": "Microbiome", "url": "https://microbiomejournal.biomedcentral.com/articles/most-recent/rss.xml"},
]

# ---------- 预印本搜索 ----------
PREPRINT_SEARCHES: list[dict[str, str]] = [
    {
        "source": "medRxiv",
        "base_url": "https://www.medrxiv.org/search/",
        "query": (
            "preventive medicine OR nutrition OR dietary intervention OR "
            "public health nutrition OR gut microbiome diet OR obesity prevention OR "
            "Mediterranean diet OR chronic disease prevention OR nutritional epidemiology OR "
            "micronutrients OR malnutrition OR food policy OR metabolic syndrome"
        ),
    },
    {
        "source": "bioRxiv",
        "base_url": "https://www.biorxiv.org/search/",
        "query": (
            "nutrition OR microbiome OR gut microbiota OR diet intervention OR "
            "metabolomics diet OR prebiotic OR probiotic OR food science"
        ),
    },
]

# ---------- ClinicalTrials.gov ----------
CT_API = "https://clinicaltrials.gov/api/v2/studies"
# Broader query terms (API is more efficient with fewer, broader queries)
CT_TERMS: list[str] = [
    "nutrition OR diet OR obesity",
    "preventive medicine OR public health",
    "gut microbiota OR microbiome",
    "diabetes prevention OR cardiovascular prevention OR metabolic syndrome",
]

# ---------- 关键词过滤 ----------
KEYWORDS: list[str] = [
    "nutrition", "diet", "dietary", "nutrient", "food",
    "obesity", "overweight", "weight loss", "body mass",
    "microbiome", "microbiota", "gut", "fiber",
    "preventive", "prevention", "public health",
    "epidemiology", "cohort", "mortality", "chronic disease",
    "cardiovascular", "diabetes", "metabolic", "hypertension",
    "Mediterranean", "DASH", "supplement", "vitamin", "mineral",
    "antioxidant", "polyphenol", "probiotic", "prebiotic",
    "aging", "longevity", "maternal", "pregnancy", "infant",
    "cancer prevention", "inflammation",
    # Chinese keywords for Chinese-language papers
    "营养", "膳食", "饮食", "肥胖", "肠道", "预防",
    "微量营养素", "益生菌", "代谢", "流行病",
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)


def _matches(text: str) -> bool:
    """Check if text contains any research keyword."""
    if not text:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in KEYWORDS)


def _clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw).strip()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y %b %d",
        "%b %d, %Y",
    ]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            # Make aware if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _safe_get(url: str, timeout: int = 30) -> Any | None:
    """Fetch URL, return Response or None on failure."""
    try:
        return Fetcher.get(url, stealthy_headers=True, timeout=timeout)
    except Exception as exc:
        print(f"    [!] HTTP error: {exc}")
        return None


# ---------------------------------------------------------------------------
# 1. PubMed E-utilities
# ---------------------------------------------------------------------------

def fetch_pubmed() -> list[dict[str, Any]]:
    """
    Use NCBI E-utilities to search for recent papers from target journals.
    Reliable, free, no authentication needed.
    Endpoint limit: 3/sec without API key, 10/sec with.
    """
    papers: list[dict[str, Any]] = []
    cutoff = _cutoff()
    print(f"[PubMed] Searching {len(TARGET_JOURNALS)} journals (past {DAYS_BACK}d) ...")

    for journal in TARGET_JOURNALS:
        # Build search: "Journal Name"[Journal] AND 2026[pdat]
        query_term = f'"{journal}"[Journal] AND {cutoff.strftime("%Y")}[pdat]'
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            f"db=pubmed&term={urllib.parse.quote(query_term)}"
            f"&retmax={MAX_PER_SOURCE}&sort=date&retmode=json"
        )

        resp = _safe_get(search_url)
        if resp is None:
            continue
        if resp.status != 200:
            continue

        try:
            search_data = json.loads(resp.body.decode("utf-8"))
        except Exception:
            continue

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            continue

        # Rate limit: 3/sec without API key
        time.sleep(0.35)

        # Get summaries
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            f"db=pubmed&id={','.join(id_list)}&retmode=json"
        )
        sum_resp = _safe_get(summary_url)
        if sum_resp is None:
            continue
        if sum_resp.status != 200:
            continue

        try:
            summary_data = json.loads(sum_resp.body.decode("utf-8"))
        except Exception:
            continue

        results = summary_data.get("result", {})
        count = 0
        for pid in id_list:
            info = results.get(pid, {})
            title = info.get("title", "")
            pub_date = info.get("pubdate", "")  # format: "2026 Jun 6"
            source = info.get("source", "")
            doi = info.get("elocationid", "").replace("doi: ", "")
            uid_list = info.get("articleids", [])

            # Get DOI URL or PubMed URL
            doi_found = ""
            pmc_id = ""
            for uid in uid_list:
                if uid.get("idtype") == "doi":
                    doi_found = uid.get("value", "")
                elif uid.get("idtype") == "pmc":
                    pmc_id = uid.get("value", "")

            url = f"https://doi.org/{doi_found}" if doi_found else f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"

            date_parsed = _parse_date(pub_date)
            if date_parsed and date_parsed < cutoff:
                continue

            if not _matches(f"{title} {source}"):
                continue

            authors_raw = info.get("authors", [])
            authors_list = []
            for a in authors_raw:
                name = a.get("name", "")
                if name:
                    authors_list.append({"name": name, "authtype": a.get("authtype", "Author")})

            paper = {
                "title": title,
                "url": url,
                "source": f"PubMed → {journal}",
                "source_type": "journal",
                "date": date_parsed.isoformat() if date_parsed else pub_date,
                "abstract": f"Journal: {source}",
                "pmid": pid,
                "authors": authors_list,
                "volume": info.get("volume", ""),
                "issue": info.get("issue", ""),
                "pages": info.get("pages", ""),
                "issn": info.get("issn", ""),
                "essn": info.get("essn", ""),
                "journal_full": info.get("fulljournalname", "") or source,
                "pub_types": info.get("pubtype", []),
                "elocationid": info.get("elocationid", ""),
                "epubdate": info.get("epubdate", ""),
            }
            papers.append(paper)
            count += 1

        if count:
            print(f"  {journal}: {count} papers")
        time.sleep(0.35)

    return papers


# ---------------------------------------------------------------------------
# 2. RSS / Atom 源
# ---------------------------------------------------------------------------

def fetch_rss() -> list[dict[str, Any]]:
    """Fetch working RSS/Atom feeds."""
    papers: list[dict[str, Any]] = []
    cutoff = _cutoff()
    print(f"[RSS] Checking {len(RSS_FEEDS)} feeds ...")

    for feed in RSS_FEEDS:
        name = feed["name"]
        url = feed["url"]
        resp = _safe_get(url)
        if resp is None or resp.status != 200:
            print(f"  {name}: FAIL (HTTP {resp.status if resp else 'error'})")
            continue

        # RSS <item> or Atom <entry>
        items = resp.css("item, entry")
        count = 0
        for item in items:
            # Title: handle both RSS and Atom
            title_el = item.css("title::text").get()
            # Link: RSS is text, Atom is href attr
            link_el = item.css("link::text").get() or item.css("link[href]::attr(href)").get()
            if not link_el:
                # Atom: <link href="..."/>
                link_el = item.xpath('.//*[local-name()="link"]/@href').get()
            desc_el = item.css("description::text, summary::text").get()
            date_el = item.css("pubDate::text, published::text, updated::text").get()

            title = _clean_html(title_el or "")
            link = _clean_html(link_el or "")
            if not title or not link:
                continue

            pub_date = _parse_date(date_el)
            if pub_date and pub_date < cutoff:
                continue

            abstract = _clean_html(desc_el or "")[:500]
            if not _matches(f"{title} {abstract}"):
                continue

            papers.append({
                "title": title,
                "url": link,
                "source": f"{name} RSS",
                "source_type": "journal",
                "date": pub_date.isoformat() if pub_date else None,
                "abstract": abstract,
            })
            count += 1

        print(f"  {name}: {count} papers")

    return papers


# ---------------------------------------------------------------------------
# 3. 预印本 (medRxiv / bioRxiv)
# ---------------------------------------------------------------------------

def fetch_preprints() -> list[dict[str, Any]]:
    """Scrape medRxiv and bioRxiv search results with browser rendering."""
    papers: list[dict[str, Any]] = []
    cutoff = _cutoff()
    print(f"[Preprints] Searching medRxiv + bioRxiv (browser mode) ...")

    for search in PREPRINT_SEARCHES:
        source = search["source"]
        query = urllib.parse.quote(search["query"])
        url = f"{search['base_url']}{query}?sorts=new%20new&numResults=50"

        print(f"  {source}: fetching (JS render)...", end=" ", flush=True)
        try:
            # Must use DynamicFetcher — titles are JS-rendered on medRxiv/bioRxiv
            resp = DynamicFetcher.fetch(url, headless=True, timeout=60000)
        except Exception as exc:
            print(f"FAIL ({exc})")
            continue

        items = resp.css(".highwire-cite")
        if not items:
            items = resp.css("li.search-result")

        count = 0
        seen: set[str] = set()
        for item in items:
            # medRxiv/bioRxiv inject titles via JS; use broad text extraction
            all_texts = item.css("*::text").getall()
            text_parts = [t.strip() for t in all_texts if t.strip()]

            # First non-empty text is usually the title
            title = text_parts[0] if text_parts else ""

            # Get DOI link
            link_el = (
                item.css(".highwire-cite-linked-title::attr(href), .highwire-cite-title a::attr(href)").get()
                or item.css("a[href*='content/10.']::attr(href)").get()
            )
            link = _clean_html(link_el or "")

            if not title or not link:
                continue
            if "content/10." not in link:
                continue
            if not link.startswith("http"):
                link = f"https://www.{source.lower()}.org{link}"

            if link in seen:
                continue
            seen.add(link)

            # Abstract from snippet
            date_el = item.css(".highwire-cite-metadata time::text, .pub-date::text, time::text").get()
            abstract_el = item.css(".highwire-cite-snippet::text, .abstract::text, p.snippet::text").get()

            pub_date = _parse_date(date_el)
            if pub_date and pub_date < cutoff:
                continue

            # Use remaining text parts as abstract/context
            abstract = _clean_html(abstract_el or "")[:500] or " ".join(text_parts[1:5])[:500]

            if not _matches(f"{title} {abstract}"):
                continue

            papers.append({
                "title": title,
                "url": link,
                "source": source,
                "source_type": "preprint",
                "date": pub_date.isoformat() if pub_date else None,
                "abstract": abstract,
            })
            count += 1

        print(f"{count} papers")
    return papers


# ---------------------------------------------------------------------------
# 4. ClinicalTrials.gov
# ---------------------------------------------------------------------------

def fetch_trials() -> list[dict[str, Any]]:
    """Query ClinicalTrials.gov API v2 for new/recent trials."""
    papers: list[dict[str, Any]] = []
    print(f"[Trials] Querying {len(CT_TERMS)} condition areas ...")

    # Comma-separated status values (required by API v2)
    status_filter = "RECRUITING,NOT_YET_RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED"

    for term in CT_TERMS:
        query = urllib.parse.quote(term)
        url = (
            f"{CT_API}?query.term={query}"
            f"&filter.overallStatus={urllib.parse.quote(status_filter)}"
            "&sort=LastUpdatePostDate:desc&pageSize=10&format=json"
        )

        resp = _safe_get(url)
        if resp is None or resp.status != 200:
            continue

        try:
            data = json.loads(resp.body.decode("utf-8"))
        except Exception:
            continue

        studies = data.get("studies", [])
        count = 0
        for study in studies:
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status_mod = protocol.get("statusModule", {})
            desc_mod = protocol.get("descriptionModule", {})
            design_mod = protocol.get("designModule", {})

            nct_id = ident.get("nctId", "")
            title = ident.get("briefTitle", "")
            official_title = ident.get("officialTitle", "")
            status = status_mod.get("overallStatus", "")
            start_date = status_mod.get("startDateStruct", {}).get("date", "")
            description = desc_mod.get("briefSummary", "")
            conditions = protocol.get("conditionsModule", {}).get("conditions", [])
            interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])

            if not _matches(f"{title} {official_title} {' '.join(conditions)}"):
                continue

            abstract_parts = [f"Status: {status}"]
            if conditions:
                abstract_parts.append(f"Conditions: {', '.join(conditions[:5])}")
            if interventions:
                intv_names = [i.get("name", "?") for i in interventions[:5]]
                abstract_parts.append(f"Interventions: {', '.join(intv_names)}")
            if description and len(description) > 10:
                abstract_parts.append(_clean_html(description)[:300])
            if design_mod.get("studyType"):
                abstract_parts.append(f"Study Type: {design_mod['studyType']}")

            papers.append({
                "title": title or official_title or nct_id,
                "url": f"https://clinicaltrials.gov/study/{nct_id}",
                "source": "ClinicalTrials.gov",
                "source_type": "trial",
                "date": start_date,
                "abstract": "; ".join(abstract_parts),
                "nct_id": nct_id,
                "status": status,
            })
            count += 1

        if count:
            print(f"  {term}: {count} trials")
        # Rate limit
        time.sleep(0.35)

    return papers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("[Scrapling] 文献抓取引擎")
    print(f"   时间范围: 过去 {DAYS_BACK} 天")
    print(f"   运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_papers: list[dict[str, Any]] = []

    # 1. PubMed
    print("\n[1/4] PubMed E-utilities")
    pubmed = fetch_pubmed()
    all_papers.extend(pubmed)
    print(f"  => 合计 {len(pubmed)} 篇")

    # 2. RSS
    print("\n[2/4] RSS/Atom 快速通道")
    rss = fetch_rss()
    all_papers.extend(rss)
    print(f"  → 合计 {len(rss)} 篇")

    # 3. Preprints
    print("\n[3/4] 预印本 (medRxiv/bioRxiv)")
    preprints = fetch_preprints()
    all_papers.extend(preprints)
    print(f"  → 合计 {len(preprints)} 篇")

    # 4. Trials
    print("\n[4/4] ClinicalTrials.gov")
    trials = fetch_trials()
    all_papers.extend(trials)
    print(f"  → 合计 {len(trials)} 篇")

    # De-duplicate by URL
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in all_papers:
        url = p.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(p)

    # Sort by date descending
    unique.sort(key=lambda p: p.get("date") or "", reverse=True)

    # Output
    result = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "days_back": DAYS_BACK,
            "total_papers": len(unique),
            "sources": {
                "pubmed": len(pubmed),
                "rss": len(rss),
                "preprints": len(preprints),
                "trials": len(trials),
            },
        },
        "papers": unique,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"[OK] 完成！去重后共 {len(unique)} 篇文献")
    print(f"   输出: {OUTPUT}")
    print(f"{'=' * 60}")

    from collections import Counter
    for st, cnt in Counter(p["source_type"] for p in unique).items():
        print(f"   {st}: {cnt}")

    # Top 5 preview
    print(f"\n=== Top 5 Preview ===")
    for i, p in enumerate(unique[:5], 1):
        title = p["title"][:100]
        src = p["source"]
        print(f"   {i}. [{src}] {title}")


if __name__ == "__main__":
    main()
