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


def build_item(p: dict, tags: list[str]) -> dict:
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
    item = {
        "itemType": "journalArticle",
        "title": title,
        "url": url or "",
        "DOI": doi,
        "abstractNote": (p.get("findings") or "")[:1000],
        "date": (p.get("date") or datetime.now(TZ).strftime("%Y-%m-%d")),
        "publicationTitle": extract_journal(source),
        "language": "en",
        "accessDate": datetime.now(TZ).strftime("%Y-%m-%d"),
        "tags": tag_objs,
        "creators": [],
        "extra": f"PMID: {pmid}" if pmid else "",
    }

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


def sync_papers(papers: list[dict], collections: dict[str, str]) -> dict:
    """同步论文到 Zotero."""
    state = load_state()
    created = 0
    skipped = 0
    errors = 0
    total = len(papers)
    write_token = None

    for i, p in enumerate(papers, 1):
        pmid = p.get("pmid", "")
        title = (p.get("original_title") or p.get("title_cn") or "unknown")[:60]

        # 去重
        if pmid and pmid in state:
            skipped += 1
            continue

        # 分类
        cols = classify_paper(p)
        tags = list(dict.fromkeys(cols))  # 去重维持顺序

        if DRY_RUN:
            print(f"  [{i}/{total}] [dry-run] {title} → {', '.join(cols[:3])}")
            created += 1
            if pmid:
                state[pmid] = "DRY_RUN"
            continue

        # 构建条目（不带 note 字段，Zotero API 不允许 journalArticle 带 note）
        item, note_html = build_item(p, tags)
        item_headers = {"Zotero-Write-Token": write_token} if write_token else None

        # 创建条目
        status, body, resp_headers = _req("POST", "/items", [item], item_headers)

        if status in (200, 201):
            if isinstance(body, dict) and "success" in body:
                item_key = body["success"].get("0", "")
            elif isinstance(body, list) and body:
                item_key = body[0] if isinstance(body[0], str) else body[0].get("key", "")
            else:
                item_key = ""
        elif status == 403 and not write_token:
            # CSRF token required
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
            print(f"  [{i}/{total}] FAIL {title}: {body}")
            errors += 1
            continue

        # 创建笔记（作为子项）
        if note_html:
            create_note(item_key, note_html, write_token)

        # 添加到集合
        for col in cols[:3]:
            col_key = collections.get(col)
            if col_key and not col_key.startswith("DRY_RUN"):
                col_headers = {"Zotero-Write-Token": write_token} if write_token else None
                s, body, _ = _req("POST", f"/collections/{col_key}/items", [item_key], col_headers)
                if s not in (200, 201, 204):
                    print(f"    [WARN] 添加集合 {col}({col_key}) 失败: {s} {body}")

        # 记录到状态文件
        if pmid:
            state[pmid] = item_key
        created += 1
        print(f"  [{i}/{total}] {title[:40]} → {', '.join(cols[:2])}")

        # 速限保护（Zotero API 约 3 req/s）
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
