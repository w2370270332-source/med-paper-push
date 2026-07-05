# med-paper-push

Daily medical literature digest with LLM-powered analysis, personalized email distribution, and Zotero auto-import. Built for preventive medicine & nutrition research.

## Features

- **4-source scraping** — PubMed E-utilities (19 journals) + RSS/Atom (8 feeds) + medRxiv/bioRxiv + ClinicalTrials.gov
- **LLM deep analysis** — 8-field structured extraction per paper (background, methods, findings, significance, limitations, relevance, relevance score 1-10) via DeepSeek
- **Personalized distribution** — per-user research area preferences, CAS quartile filter, push frequency/time, relevance threshold
- **Zotero auto-import** — one-click sync with 14 research-area collections, complete metadata (authors, volume, issue, pages, ISSN)
- **Web dashboard** — Next.js 16 + Ant Design, Supabase Auth with invite codes, admin user management, email recipient management
- **HTML email digest** — cards sorted by relevance score with bilingual titles, citation metadata, and color-coded LLM analysis
- **Dual-cron reliability** — GitHub Actions (primary) + Vercel cron (backup trigger), concurrency-gated to prevent duplicate sends
- **Obsidian integration** — auto-generate structured notes in Obsidian vault for knowledge base accumulation

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│  cron: 0 0 * * * (UTC) / Vercel cron: 15 0 * * *       │
├─────────────────────────────────────────────────────────┤
│  scraper.py          analyze.py        distribute.py    │
│  ┌──────────┐       ┌──────────┐       ┌────────────┐  │
│  │ PubMed   │       │ DeepSeek │       │ QQ SMTP    │  │
│  │ RSS/Atom │  ──▶  │ API      │  ──▶  │ per-user   │  │
│  │ Preprint │       │ 8-field  │       │ HTML email │  │
│  │ Trials   │       │ analysis │       │            │  │
│  └──────────┘       └──────────┘       └────────────┘  │
│       │                   │                   │         │
│       ▼                   ▼                   ▼         │
│  scraped_papers     analysis_daily     Supabase         │
│  .json              .json              paper_pool       │
│                                                    │    │
│  sync_to_supabase.py ◀────────────────────────────┘    │
│  zotero_sync.py ──▶ Zotero API (14 collections)        │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    Vercel (Next.js 16)                   │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Dashboard  │  │ User Admin   │  │ Email Recipient│  │
│  │ preferences│  │ management   │  │ management     │  │
│  └────────────┘  └──────────────┘  └────────────────┘  │
│                         │                               │
│                    Supabase                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │ user_preferences │ paper_pool │ invite_codes     │   │
│  │ push_history     │ email_recipients              │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Research Areas (17 categories)

药食同源与植物化学物 | 高尿酸血症与痛风 | 肠道菌群 | 炎症与免疫 | 肥胖与代谢 | 心血管与代谢疾病 | 糖尿病与血糖管理 | 营养流行病学 | 公共卫生营养 | 母婴营养 | 衰老与营养 | 膳食干预与临床营养 | 综述与Meta分析 | 人工智能与数字健康 | 环境与职业健康 | 流行病与卫生统计学 | 全球健康

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+
- [Supabase](https://supabase.com) project
- [DeepSeek API key](https://platform.deepseek.com)
- QQ email account (for SMTP sending)
- [Zotero](https://www.zotero.org) account (optional, for auto-import)

### 1. Clone & install

```bash
git clone https://github.com/w2370270332-source/med-paper-push.git
cd med-paper-push

# Python deps
pip install -r requirements.txt
playwright install chromium --with-deps

# Web deps
cd web && npm install && cd ..
```

### 2. Set environment secrets

Add these to your GitHub repository secrets (Settings → Secrets and variables → Actions):

| Secret | Description |
|--------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key for LLM analysis |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service_role key |
| `EMAIL_SMTP_HOST` | SMTP server (e.g. `smtp.qq.com`) |
| `EMAIL_SMTP_PORT` | SMTP port (e.g. `465`) |
| `EMAIL_SENDER` | Sender email address |
| `EMAIL_PASSWORD` | SMTP auth code |
| `ZOTERO_API_KEY` | Zotero API key (optional) |
| `ZOTERO_USER_ID` | Zotero numeric user ID (optional) |

### 3. Set up Supabase

Run the SQL in [`web/schema.sql`](web/schema.sql) in your Supabase SQL Editor to create all tables and functions.

### 4. Deploy web UI

```bash
cd web
npx vercel --prod
```

Set the following environment variables in Vercel:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`
- `DEEPSEEK_API_KEY`

### 5. Test locally

```bash
# Scrape + analyze
python scraper.py
python analyze.py --mode daily

# Sync to Supabase
SUPABASE_URL=xxx SUPABASE_SERVICE_KEY=xxx python sync_to_supabase.py daily

# Dry-run Zotero sync
python zotero_sync.py --dry-run

# Test distribution
SUPABASE_URL=xxx SUPABASE_SERVICE_KEY=xxx DISTRIBUTE_FORCE=1 python distribute.py
```

## Pipeline

| Script | Purpose |
|--------|---------|
| `scraper.py` | Multi-source literature fetcher (PubMed + RSS + preprints + trials) |
| `analyze.py` | LLM deep analysis — 8 fields per paper via DeepSeek API |
| `sync_to_supabase.py` | Upsert analyzed papers into Supabase paper_pool |
| `zotero_sync.py` | Create Zotero items with collections, authors, volume/issue/pages |
| `distribute.py` | Match papers to users, send HTML email via QQ SMTP |
| `report_generator.py` | Generate daily/weekly markdown reports |
| `obsidian_notes.py` | Export structured notes to Obsidian vault |
| `daily_reminder.py` | Email reminder for daily paper review |

## Web UI

Built with Next.js 16 App Router + Ant Design 5 + Supabase.

| Page | Path | Features |
|------|------|----------|
| Dashboard | `/dashboard` | 17-area checkboxes, push time/frequency, relevance threshold slider, natural language interest description |
| Admin — Users | `/admin` | User list, enable/disable, edit preferences in modal |
| Admin — Emails | `/admin/email-recipients` | Add email-only recipients without registration |

Registration requires an invite code (managed via `invite_codes` table).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Scraping | [Scrapling](https://github.com/D4Vinci/Scrapling) + Playwright + PubMed E-utilities |
| LLM | DeepSeek (deepseek-chat), OpenAI-compatible API |
| Database | Supabase (PostgreSQL) with RLS |
| Backend | Python scripts orchestrated by GitHub Actions |
| Frontend | Next.js 16 + Ant Design 5 + Tailwind CSS 4 |
| Auth | Supabase Auth + email invite codes |
| Email | QQ SMTP (smtplib.SMTP_SSL) + HTML templates |
| Reference | Zotero REST API (batch create + collections) |
| Scheduling | GitHub Actions cron + Vercel cron dual trigger |
| Deploy | Vercel (web) + GitHub Actions (pipeline) |

## License

MIT

---

Built with [Claude Code](https://claude.ai/code).
