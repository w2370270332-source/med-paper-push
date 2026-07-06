#!/usr/bin/env python3
"""将分析后的论文自动导入 Zotero 并分类整理."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANALYSIS_FILE = ROOT / "analysis_daily.json"
STATE_FILE = ROOT / "zotero_sync_state.json"
TZ = timezone(timedelta(hours=8))

API_KEY = os.environ.get("ZOTERO_API_KEY", "")
USER_ID = os.environ.get("ZOTERO_USER_ID", "")
BASE = f"https://api.zotero.org/users/{USER_ID}" if USER_ID else ""
DRY_RUN = "--dry-run" in sys.argv

# 研究领域到 Zotero 集合的映射（关键词用于自动分类）
COLLECTIONS = {
    "药食同源与植物化学物": ["药食同源", "植物化学", "类黄酮", "黄酮", "多酚", "柑橘", "柚皮苷", "橙皮苷",
                    "flavonoid", "polyphenol", "citrus", "naringin", "hesperidin", "phytochemical", "bioactive", "functional food"],
    "高尿酸血症与痛风": ["高尿酸", "尿酸", "痛风", "嘌呤", "hyperuricemia", "uric acid", "gout", "xanthine oxidase"],
    "肠道菌群": ["肠道", "菌群", "微生物", "肠道菌", "microbiome", "microbiota", "gut", "flora"],
    "炎症与免疫": ["炎症", "抗炎", "免疫", "细胞因子", "inflammation", "anti-inflammatory", "cytokine", "NF-kB", "NLRP3"],
    "肥胖与代谢": ["肥胖", "减重", "bmi", "体重", "代谢", "obesity", "adipose", "weight", "metabolic"],
    "心血管与代谢疾病": ["心血管", "心脏病", "血压", "高血压", "动脉硬化", "cardiovascular", "hypertension", "heart", "blood pressure"],
    "糖尿病与血糖管理": ["糖尿病", "血糖", "胰岛素", "t2dm", "diabetes", "glucose", "insulin"],
    "营养流行病学": ["流行病学", "队列", "观察", "epidemiology", "cohort", "population"],
    "公共卫生营养": ["公共卫生", "政策", "指南", "public health", "policy", "guideline"],
    "母婴营养": ["母婴", "孕期", "妊娠", "母乳", "婴幼儿", "maternal", "pregnancy", "lactation", "infant"],
    "衰老与营养": ["衰老", "老龄", "老年", "aging", "elderly", "older"],
    "膳食干预与临床营养": ["膳食", "饮食", "干预", "临床营养", "diet", "dietary", "intervention", "clinical nutrition", "RCT", "trial"],
    "综述与Meta分析": ["meta-analysis", "systematic review", "荟萃分析", "系统综述", "meta analysis"],
    "未分类": [],
}


def _req(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple:
    """统一 Zotero API 请求."""
    url = f"{BASE}/{path.lstrip('/')}"
    h = {"Zotero-API-Key": API_KEY, "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        return e.code, {"error": body_text}, dict(e.headers) if hasattr(e, "headers") else {}
    except Exception as e:
        return 0, {"error": str(e)}, {}


def classify_paper(p: dict) -> list[str]:
    """按关键词将论文分类到 Zotero 集合."""
    combined = " ".join([
        p.get("title_cn") or "", p.get("original_title") or "",
        p.get("findings") or "", p.get("significance") or "",
        p.get("relevance") or "",
    ]).lower()
    matched = []
    for col, keywords in COLLECTIONS.items():
        if col == "未分类":
            continue
        if keywords and any(kw in combined for kw in keywords):
            matched.append(col)
    return matched or ["未分类"]


def extract_journal(source: str) -> str:
    """从来源字符串提取期刊名（去除前缀）."""
    return source.split("→")[-1].strip() if "→" in source else source[:80]


def _parse_author_name(name: str) -> dict:
    """解析 PubMed 作者名 'Last AB' 为 Zotero creator 格式."""
    name = name.strip()
    if not name:
        return {"creatorType": "author", "name": ""}
    # "Last AB" or "Last A" or "Last AB C" format
    parts = name.split()
    if len(parts) == 1:
        return {"creatorType": "author", "name": name}
    last = parts[0]
    first = " ".join(parts[1:])
    return {"creatorType": "author", "lastName": last, "firstName": first}


def build_item(p: dict, tags: list[str], collections: dict[str, str]) -> dict:
    """构建 Zotero 条目 JSON."""
    source = p.get("source", "")
    url = p.get("url", "")
    pmid = p.get("pmid", "")
    doi = ""
    doi_m = re.search(r"10\.\d{4,}/[^\s]+", url)
    if doi_m:
        doi = doi_m.group()
        if doi.endswith((".", ";")):
            doi = doi[:-1]

    # 如果 URL 中没有 DOI，检查 elocationid
    if not doi:
        eloc = p.get("elocationid", "")
        doi_m = re.search(r"10\.\d{4,}/[^\s]+", eloc)
        if doi_m:
            doi = doi_m.group().rstrip(".;")

    # 作者
    authors = p.get("authors", [])
    creators = [_parse_author_name(a["name"]) for a in authors if a.get("name")] if authors else []

    # Tag objects
    tag_objs = [{"tag": t} for t in tags[:8]]

    # 构建 rich-text 笔记
    background = p.get("background") or ""
    methods = p.get("methods") or ""
    findings = p.get("findings") or ""
    significance = p.get("significance") or ""
    limitation = p.get("limitation") or ""

    note_lines = []
    if background:
        note_lines.append(f"<p><b>研究背景：</b>{background}</p>")
    if methods:
        note_lines.append(f"<p><b>方法：</b>{methods}</p>")
    if findings:
        note_lines.append(f"<p><b>核心发现：</b>{findings}</p>")
    if significance:
        note_lines.append(f"<p><b>意义：</b>{significance}</p>")
    if limitation:
        note_lines.append(f"<p><b>局限性：</b>{limitation}</p>")

    note_html = "\n".join(note_lines) if note_lines else ""

    title = p.get("original_title") or p.get("title_cn") or ""

    # extra 字段：PMID + ISSN
    extra_parts = []
    if pmid:
        extra_parts.append(f"PMID: {pmid}")
    issn = p.get("issn", "")
    if issn:
        extra_parts.append(f"ISSN: {issn}")

    item = {
        "itemType": "journalArticle",
        "title": title,
        "url": url or "",
        "DOI": doi,
        "abstractNote": (p.get("findings") or "")[:1000],
        "date": (p.get("date") or datetime.now(TZ).strftime("%Y-%m-%d")),
        "publicationTitle": p.get("journal_full") or extract_journal(source),
        "language": "en",
        "accessDate": datetime.now(TZ).strftime("%Y-%m-%d"),
        "tags": tag_objs,
        "creators": creators,
        "extra": "; ".join(extra_parts),
    }

    volume = p.get("volume", "")
    if volume:
        item["volume"] = volume
    issue = p.get("issue", "")
    if issue:
        item["issue"] = issue
    pages = p.get("pages", "")
    if pages:
        item["pages"] = pages
    issn_val = p.get("issn", "")
    if issn_val:
        item["ISSN"] = issn_val

    # 指定集合（创建时一步到位，不需要二次 API 调用）
    col_keys = [collections.get(c) for c in tags[:3]]
    item["collections"] = [k for k in col_keys if k and not k.startswith("DRY_RUN")]

    return item, note_html


def create_note(parent_key: str, note_html: str, write_token: str | None = None):
    """为 Zotero 条目创建子笔记."""
    if not note_html or not parent_key:
        return
    note_item = {
        "itemType": "note",
        "parentItem": parent_key,
        "note": f"<div>{note_html}</div>",
    }
    extra = {"Zotero-Write-Token": write_token} if write_token else None
    _req("POST", "/items", [note_item], extra)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_collections() -> dict[str, str]:
    """查找/创建 Zotero 集合，返回 {名称: key}."""
    print("[collections] 加载现有集合...")
    _, data, _ = _req("GET", "/collections?limit=100")
    existing = {}
    if isinstance(data, list):
        for c in data:
            name = c.get("data", {}).get("name", "")
            if name:
                existing[name] = c["key"]

    collection_keys = {}
    for name in COLLECTIONS:
        if name in existing:
            collection_keys[name] = existing[name]
        else:
            if DRY_RUN:
                print(f"  [dry-run] 将创建: {name}")
                collection_keys[name] = f"DRY_RUN_{name}"
                continue
            print(f"  创建集合: {name}...", end=" ", flush=True)
            status, data, _ = _req("POST", "/collections", [{"name": name}])
            if status in (200, 201):
                result = data.get("success", {})
                if result:
                    key = list(result.values())[0] if isinstance(result, dict) else result[0]
                    collection_keys[name] = key
                    print(f"OK ({key})")
                else:
                    print(f"FAIL (no success key in response)")
            else:
                print(f"FAIL ({status}): {data}")

    return collection_keys


def _extract_doi(p: dict) -> str:
    """从论文数据提取 DOI（标准化小写）."""
    doi = ""
    # 直接从 URL 提取
    url = p.get("url", "")
    doi_m = re.search(r"10\.\d{4,}/[^\s.;]+", url)
    if doi_m:
        doi = doi_m.group().rstrip(".;")
    # 从 elocationid 提取
    if not doi:
        eloc = p.get("elocationid", "")
        doi_m = re.search(r"10\.\d{4,}/[^\s.;]+", eloc)
        if doi_m:
            doi = doi_m.group().rstrip(".;")
    return doi.strip().lower() if doi else ""


def _dedup_key(p: dict) -> str:
    """生成稳定的去重键，优先级: PMID > DOI > NCT > URL."""
    pmid = p.get("pmid", "").strip()
    if pmid:
        return f"pmid:{pmid}"
    nct = p.get("nct_id", "").strip()
    if nct:
        return f"nct:{nct}"
    doi = _extract_doi(p)
    if doi:
        return f"doi:{doi}"
    url = p.get("url", "").strip().rstrip("/")
    if url:
        return f"url:{url}"
    # 最后手段：标题哈希
    title = (p.get("original_title") or p.get("title_cn") or "").strip().lower()
    if title:
        import hashlib
        return f"title:{hashlib.sha256(title.encode()).hexdigest()[:16]}"
    return ""


def _find_existing_by_doi_zotero(doi: str, max_scan: int = 300) -> str | None:
    """在 Zotero 库中按 DOI 搜索已有条目（Layer 2 后备去重）."""
    if not doi or not BASE:
        return None
    doi_lower = doi.strip().lower()
    start = 0
    limit = 100
    scanned = 0
    while scanned < max_scan:
        status, data, headers = _req(
            "GET",
            f"/items?itemType=journalArticle&limit={limit}&start={start}"
        )
        if status != 200 or not isinstance(data, list):
            return None
        for item in data:
            item_doi = (item.get("data", {}) or {}).get("DOI", "").strip().lower()
            if item_doi == doi_lower:
                return item.get("key") or item.get("data", {}).get("key", "")
        scanned += len(data)
        total = int(headers.get("Total-Results", "0"))
        if start + limit >= total:
            break
        start += limit
        time.sleep(0.5)
    return None


def sync_papers(papers: list[dict], collections: dict[str, str]) -> dict:
    """同步论文到 Zotero，双层去重."""
    state = load_state()
    created = 0
    skipped = 0
    errors = 0
    total = len(papers)
    write_token = None

    # Layer-2 缓存：本次运行中已查询过的 DOI
    _doi_cache: dict[str, str | None] = {}

    for i, p in enumerate(papers, 1):
        title_short = (p.get("original_title") or p.get("title_cn") or "unknown")[:60]
        dkey = _dedup_key(p)

        # Layer 1: 本地状态文件去重
        if dkey and dkey in state:
            skipped += 1
            continue

        # Layer 2: Zotero API 查询（仅对非 PMID 论文，且有 DOI）
        doi = _extract_doi(p)
        if (not dkey or not dkey.startswith("pmid:")) and doi and not DRY_RUN:
            if doi not in _doi_cache:
                _doi_cache[doi] = _find_existing_by_doi_zotero(doi)
            existing = _doi_cache[doi]
            if existing:
                # 补录到本地状态
                if dkey:
                    state[dkey] = existing
                skipped += 1
                continue

        # 分类
        cols = classify_paper(p)
        tags = list(dict.fromkeys(cols))

        if DRY_RUN:
            print(f"  [{i}/{total}] [dry-run] {title_short} → {', '.join(cols[:3])}")
            created += 1
            if dkey:
                state[dkey] = "DRY_RUN"
            continue

        # 构建条目并创建
        item, note_html = build_item(p, tags, collections)
        item_headers = {"Zotero-Write-Token": write_token} if write_token else None

        status, body, resp_headers = _req("POST", "/items", [item], item_headers)

        if status in (200, 201):
            if isinstance(body, dict) and "success" in body:
                item_key = body["success"].get("0", "")
            elif isinstance(body, list) and body:
                item_key = body[0] if isinstance(body[0], str) else body[0].get("key", "")
            else:
                item_key = ""
        elif status == 403 and not write_token:
            token = resp_headers.get("Zotero-Write-Token", "")
            if token:
                write_token = token
                status, body, resp_headers = _req("POST", "/items", [item], {"Zotero-Write-Token": token})
                item_key = body.get("success", {}).get("0", "") if isinstance(body, dict) else ""
            else:
                item_key = ""
        else:
            item_key = ""

        if not item_key:
            print(f"  [{i}/{total}] FAIL {title_short}: {body}")
            errors += 1
            continue

        # 创建笔记
        if note_html:
            create_note(item_key, note_html, write_token)

        # 记录到状态文件（所有论文，不止 PMID）
        if dkey:
            state[dkey] = item_key
        created += 1
        print(f"  [{i}/{total}] {title_short[:40]} → {', '.join(cols[:2])}")

        if i < total:
            time.sleep(1.0)

    if not DRY_RUN:
        save_state(state)

    return {"created": created, "skipped": skipped, "errors": errors}


def main():
    if not API_KEY or not USER_ID:
        print("[ERROR] 请设置 ZOTERO_API_KEY 和 ZOTERO_USER_ID 环境变量")
        print("  API Key: https://www.zotero.org/settings/keys")
        print("  User ID: https://www.zotero.org/settings/keys (显示在页面顶部)")
        return 0  # 非致命错误

    if not ANALYSIS_FILE.exists():
        print(f"[INFO] {ANALYSIS_FILE} 不存在，跳过 Zotero 同步")
        return 0

    with open(ANALYSIS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    papers = data.get("papers", [])

    if not papers:
        print("[INFO] 无论文数据，跳过")
        return 0

    print(f"[zotero] {len(papers)} 篇论文，模式: {'dry-run' if DRY_RUN else '正式'}")

    collections = ensure_collections()
    result = sync_papers(papers, collections)

    print(f"同步完成: 新建 {result['created']} | 跳过 {result['skipped']} | 失败 {result['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
