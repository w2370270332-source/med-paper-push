#!/usr/bin/env python3
"""文献推送完整流水线：抓取 → 报告 → 邮件 → Obsidian."""

import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))


def step(name: str, args: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    result = subprocess.run(args, cwd=str(ROOT), env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    return result.returncode == 0


def main():
    today = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    print(f"文献推送流水线启动 — {today}")
    print(f"工作目录: {ROOT}")

    # Phase 1: 抓取
    if not step("Phase 1/4: Scrapling 多源抓取", [sys.executable, "scraper.py"]):
        print("[ERROR] 抓取失败，流水线中止")
        return 1

    # Phase 2: 生成报告
    if not step("Phase 2/4: 生成报告", [sys.executable, "generate_report.py"]):
        print("[ERROR] 报告生成失败，流水线中止")
        return 1

    # Phase 3: 发送邮件
    step("Phase 3/5: 邮件发送", [sys.executable, "send_email.py"])

    # Phase 4: 飞书推送
    step("Phase 4/5: 飞书推送", [sys.executable, "feishu_push.py"])

    # Phase 5: 保存到 Obsidian vault
    report = ROOT / "report.md"
    if report.exists():
        vault = Path("G:/obsidian/Inbox")
        if vault.exists():
            date_str = datetime.now(TZ).strftime("%Y%m%d")
            obs_path = vault / f"文献周报-{date_str}.md"
            obs_path.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"\n[OK] Obsidian: {obs_path}")
        else:
            print(f"\n[WARN] Obsidian vault 不存在: {vault}")

    print(f"\n{'='*60}")
    print(f"  流水线完成 — {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}")
    print(f"  报告: {ROOT / 'report.md'}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
