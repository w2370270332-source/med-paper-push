# 项目：预防医学与营养学文献推送（med-paper-push）

## 项目位置
`g:/vs/med-paper-push/`

## 项目性质
预防医学与营养学方向的学术文献追踪项目，每天自动检索最新论文和进展，提炼摘要推送至飞书。

## 文献检索管线

### 第一阶段：Scrapling 多源抓取（`scraper.py`）
使用 Scrapling 从四个渠道并行抓取，输出 `scraped_papers.json`：

| 渠道 | 方法 | 覆盖 |
|------|------|------|
| PubMed E-utilities | API 查询 19 种目标期刊 | NEJM, Lancet, JAMA, BMJ, Nat Med, AJCN, J Nutr, EJCN, PHN, Nutrients, IJO, Obes Rev, Prev Med, AJPM, IJE, AJE, Epidemiology, Gut Microbes, Microbiome |
| RSS/Atom 快速通道 | Nature/PLOS/BMC 源 | 比 PubMed 快 0-1 天 |
| medRxiv/bioRxiv | DynamicFetcher (JS 渲染) | 预印本，PubMed 未收录 |
| ClinicalTrials.gov | JSON API v2 | 营养/预防/肠道菌群相关新试验 |

运行：`python scraper.py`

### 第二阶段：AnySearch 补充检索
- `academic.biomedical` — PubMed/MEDLINE 补充（跨期刊搜索，覆盖第一阶段未覆盖的期刊）
- `academic.search` — 跨学科检索
- `academic.preprint` — 额外预印本

### 第三阶段：合并去重 → report.md
将 Scrapling 输出 + AnySearch 结果合并，去重，按日期和研究重要性排序，生成最终报告。

## 研究领域关键词
- Preventive Medicine（预防医学）
- Nutritional Epidemiology（营养流行病学）
- Dietary Intervention（膳食干预）
- Public Health Nutrition（公共卫生营养）
- Chronic Disease Prevention（慢性病预防）
- Micronutrients & Macronutrients（微量/宏量营养素）
- Gut Microbiome & Diet（肠道菌群与饮食）
- Food Policy & Dietary Guidelines（食品政策与膳食指南）
- Mediterranean Diet / DASH Diet（地中海饮食/DASH饮食）
- Obesity Prevention（肥胖预防）
- Nutrition & Aging（营养与衰老）
- Maternal & Child Nutrition（母婴营养）

## 筛选策略
- 时间：过去 24 小时 ~ 7 天
- 优先：Meta-Analysis > Systematic Review > RCT > Cohort Study
- 关注高影响因子期刊
- 中文为主输出，保留英文关键术语

## 输出格式要求

每天推送摘要包含：
- 日期和覆盖范围
- 3-5 条最重要发现
- 每条：标题（中英）、来源、一句话要点、为什么重要
- 底部标注搜索来源

## 工具链
- **Scrapling** (scraper.py)：多源文献抓取引擎
- **AnySearch**：补充学术搜索
- **send_email.py**：通过 QQ 邮箱 SMTP 发送 report.md 到飞书
- **运行模式**：auto（自动执行，无需人工确认）

## 文件说明
```
med-paper-push/
  CLAUDE.md          — 本文件
  scraper.py         — Scrapling 多源抓取引擎（PubMed+RSS+预印本+试验）
  scraped_papers.json — 抓取结果输出
  send_email.py      — 邮件推送脚本（QQ邮箱 → 飞书）
  report.md          — 每日推送报告
  .claude/           — Claude 配置
  memory/            — 项目记忆
```
