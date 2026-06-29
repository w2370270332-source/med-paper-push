#!/usr/bin/env python3
"""将论文分析结果同步到 Supabase paper_pool 表."""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))


def _parse_date(raw: str | None) -> str:
    """将各种日期格式统一为 YYYY-MM-DD."""
    if not raw:
        return datetime.now(TZ).strftime("%Y-%m-%d")
    raw = raw.strip()
    # 已经是标准格式
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw
    # "2026 Jun" / "2026-06" 等不完整格式
    import re
    # "2026 Jun" -> look up month
    m = re.match(r"(\d{4})\s+(\w{3,})", raw)
    if m:
        year = m.group(1)
        month_abbr = m.group(2)[:3].lower()
        months = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
                  "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
        if month_abbr in months:
            return f"{year}-{months[month_abbr]}-01"
    # "2026-06" -> fill day
    m = re.match(r"(\d{4})-(\d{1,2})$", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    # fallback
    return datetime.now(TZ).strftime("%Y-%m-%d")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")  # service_role key


def load_analysis(mode: str) -> list[dict]:
    path = ROOT / f"analysis_{mode}.json"
    if not path.exists():
        print(f"[WARN] {path} 不存在")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("papers", [])


def sync_papers(papers: list[dict], mode: str) -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL 或 SUPABASE_SERVICE_KEY 未设置")
        return 0

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    count = 0

    for p in papers:
        pmid = p.get("pmid", "")
        title = p.get("original_title", "") or p.get("title_cn", "")
        if not title:
            continue

        # 检查是否已存在 → 刷新 fetched_at 保持新鲜度
        existing_id = _find_existing_id(pmid, title)
        if existing_id:
            _refresh_fetched_at(existing_id)
            count += 1
            continue

        body = json.dumps({
            "pmid": pmid,
            "title": title[:500],
            "title_cn": (p.get("title_cn") or "")[:500],
            "original_title": (p.get("original_title") or "")[:500],
            "source": (p.get("source") or "")[:200],
            "url": (p.get("url") or "")[:500],
            "study_type": (p.get("study_type") or ""),
            "background": (p.get("background") or "")[:1000],
            "methods": (p.get("methods") or "")[:1000],
            "findings": (p.get("findings") or "")[:1000],
            "significance": (p.get("significance") or "")[:500],
            "limitation": (p.get("limitation") or "")[:500],
            "relevance": (p.get("relevance") or "")[:500],
            "pub_date": _parse_date(p.get("date")),
            "fetched_at": datetime.now(TZ).isoformat(),
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/paper_pool",
            data=body,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                pass
            count += 1
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200] if e.fp else ""
            print(f"  [WARN] 插入失败 ({title[:40]}): {e.code} {err_body}")
        except Exception as e:
            print(f"  [WARN] 插入失败 ({title[:40]}): {e}")

    print(f"[sync:{mode}] 同步 {count}/{len(papers)} 篇论文到 Supabase")
    return count


def _find_existing_id(pmid: str, title: str) -> int | None:
    """查找已有论文 ID，不存在返回 None."""
    if pmid:
        url = f"{SUPABASE_URL}/rest/v1/paper_pool?pmid=eq.{pmid}&select=id&limit=1"
    else:
        encoded = urllib.parse.quote(title[:50])
        url = f"{SUPABASE_URL}/rest/v1/paper_pool?title=ilike.*{encoded}*&select=id&limit=1"

    req = urllib.request.Request(
        url,
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data[0]["id"] if data else None
    except Exception:
        return None


def _refresh_fetched_at(paper_id: int) -> None:
    """刷新论文的 fetched_at 时间戳."""
    body = json.dumps({"fetched_at": datetime.now(TZ).isoformat()}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/paper_pool?id=eq.{paper_id}",
        data=body,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    papers = load_analysis(mode)
    if not papers:
        return 1
    sync_papers(papers, mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
