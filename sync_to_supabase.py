#!/usr/bin/env python3
"""将论文分析结果同步到 Supabase paper_pool 表."""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))

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

        # 检查是否已存在
        existing = _find_existing(pmid, title)
        if existing:
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
            "pub_date": p.get("date") or today,
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


def _find_existing(pmid: str, title: str) -> bool:
    """检查论文是否已在库中."""
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
        return len(data) > 0
    except Exception:
        return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    papers = load_analysis(mode)
    if not papers:
        return 1
    sync_papers(papers, mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
