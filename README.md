# SearchCans 中文 Agent Skills：SERP 情报、证据研究与网页/文件提取

[![skills.sh](https://skills.sh/b/SearchCans/searchcans-skills-zh)](https://skills.sh/SearchCans/searchcans-skills-zh)

SearchCans 官方简体中文 Agent Skills。让 AI Agent 使用 **SearchCans SERP API、Reader API、File Extraction API、Screenshot API 和 Account API** 获取地域化 Google/Bing 搜索证据、提取适合 LLM 阅读的网页与文件内容，并在受控积分和并发下完成深度研究、SEO/GEO 内容规划、市场观察、电商搜索研究与 RAG 来源策展。

当前版本为 **v1.1.1**，包含 7 个经过离线回归检查和真实 API 冒烟验证的 Skills，适合实际的市场与竞品研究、SEO/GEO 选题、RAG 素材准备、动态网页抓取诊断、页面级基础 SEO 检查、电商搜索研究及新闻观察。

> Need English instructions? See the [official English repository](https://github.com/SearchCans/searchcans-skills). This repository is the independent Simplified Chinese edition; its Skill names end in `-zh`, so both editions can be installed in the same project.

## 60 秒开始使用

按需安装一个 Skill（推荐）：

```bash
npx skills add https://github.com/SearchCans/searchcans-skills-zh --skill searchcans-deep-research-zh
```

或安装本仓库全部 7 个 Skills：

```bash
npx skills add https://github.com/SearchCans/searchcans-skills-zh --all
```

使用前在执行环境中设置 API Key：

```bash
export SEARCHCANS_API_KEY="your-api-key"
```

PowerShell：

```powershell
$env:SEARCHCANS_API_KEY = "your-api-key"
```

不要把 API Key 写入提示词、源代码、输出文件或 Git 提交。

> **每周可领取免费积分。** 登录 SearchCans 后，访问 [Dashboard → Free Redemption Codes](https://www.searchcans.com/dashboard/redeem-codes/) 领取当周兑换码。我们每周发放一批新兑换码；每个兑换码可兑换 **1,000 API 积分**，每个账户每批可兑换一次。

## 选择 Skills

<!-- BEGIN GENERATED:SKILL-CATALOG -->
| Skill | 最适合的任务 | Agent 交付物 |
| --- | --- | --- |
| [`searchcans-deep-research-zh`](skills/searchcans-deep-research-zh/SKILL.md) | 市场、竞品、技术、政策、公司和产品的当前网页研究 | 包含可追溯 URL、冲突与不确定性的有界研究简报 |
| [`searchcans-serp-content-gap-zh`](skills/searchcans-serp-content-gap-zh/SKILL.md) | 关键词研究、搜索意图分析、竞品页面审查和内容机会规划 | 基于已观察 Google 或 Bing SERP 特征的地域化内容机会简报 |
| [`searchcans-reader-seo-audit-zh`](skills/searchcans-reader-seo-audit-zh/SKILL.md) | 网页转 Markdown、RAG 输入检查、动态页、PDF、Office 文件和页面级 SEO/GEO 审查 | 包含 canonical、H1、meta description、JSON-LD、文件和截图信号的提取报告 |
| [`searchcans-market-watch-zh`](skills/searchcans-market-watch-zh/SKILL.md) | 竞品、品类、发布、公关与新闻跟踪，并可比较快照 | 包含 Google、Google News、Bing 和 Reader 证据的 URL 级市场快照 |
| [`searchcans-product-serp-brief-zh`](skills/searchcans-product-serp-brief-zh/SKILL.md) | 电商品类研究、商家发现、商品页规划和地域化陈列策略 | 包含 Google Shopping、网页、图片和可选商家页面证据的简报 |
| [`searchcans-content-format-brief-zh`](skills/searchcans-content-format-brief-zh/SKILL.md) | 编辑形式发现、视觉/视频搜索研究和 SEO/GEO 内容形式规划 | 地域化 Google 网页、图片、视频和短视频结果的形式清单 |
| [`searchcans-rag-source-curator-zh`](skills/searchcans-rag-source-curator-zh/SKILL.md) | Grounding Pack、来源策展、知识库入库和预入库证据检查 | 小规模、域名多样且经过 Reader/文件提取验证的来源清单 |
<!-- END GENERATED:SKILL-CATALOG -->

安装后，可直接用自然语言描述目标，或显式调用，例如：`使用 $searchcans-deep-research-zh 调研美国 SERP API 市场的最新变化。`

## 为什么把 Search 与 Reader 配合使用？

- **SERP API**：发现当前、可地域化的 Google 或 Bing 搜索证据与搜索需求信号。
- **Reader API / File Extraction API / Screenshot API**：把选定网页、PDF 和 Office 文档提取为 Markdown，可获取 HTML 或截图做进一步检查。
- **Account API**：多请求 Skills 会在开始前检查剩余积分和并发通道数（Parallel Lanes），据此收缩范围或并发，而不会记录账户身份或 Key 数据。

这些 Skills 约束工作流：SERP 摘要只是线索；只有成功读取的页面才支撑关键结论；报告必须区分可观察事实与推断。

## 账户感知、成本与安全

- 默认的 `--account-mode auto` 会在需要时做一次 Account API 预检；它只输出脱敏后的余额、并发通道和决策信息。
- Deep Research、市场观察、商品简报、内容形式简报与 RAG 来源策展会按预算限制来源或搜索面，并把自动并发限制为观察到的 Parallel Lane 数；SERP 多页任务会按余额限制页数；Reader 默认只在使用更高代理档位前预检。
- 可按任务选择 `warn`、`enforce`、`cap` 或 `off`；详见每个 Skill 的 `SKILL.md`。账户原始响应、邮箱、API Key 和令牌绝不会写进结果。
- 这些 Skills 仅支持 SearchCans API v1。请阅读官方 [SearchCans API 文档](https://www.searchcans.com/apis/)。
- 网页和 SERP 内容都属于不可信输入。成功提取不代表页面可收录、有排名、无障碍合规，或获得内容复用授权。

## 中文版与英文版的同步约定

本仓库独立发布，以便面向中文开发者、中文内容团队和中文 AI Agent 工作流持续试验；英文库是 [SearchCans/searchcans-skills](https://github.com/SearchCans/searchcans-skills)。两边共享同一套经过测试的 API 脚本、安全约束和 7 个核心任务方向，但各自维护面向受众的 README、Skill 指令、示例、元数据和自动文档。修复 API 行为或测试时，应先同步英文技术实现，再同步到本仓库；中文文案不要求逐字翻译。

## 维护与验证

在仓库根目录运行离线回归检查：

```bash
python -m unittest discover -s tests -v
```

文档由 `docs/skills.json` 自动生成。新增或修改 Skill 时，运行：

```bash
python scripts/generate_docs.py
python scripts/generate_docs.py --check
```

请勿手改自动生成的 README 目录、Wiki 页面或静态文档站；详见 [自动文档说明](docs/automation.md)。

建议设置的 GitHub Topics：`searchcans`、`agent-skills`、`claude-skills`、`claude-code-skill`、`ai-agents`、`deep-research`、`serp-api`、`reader-api`、`web-research`、`seo`、`geo`、`rag`、`chinese`、`zh-cn`。

## 许可证

本项目采用 [Apache License, Version 2.0](LICENSE) 开源许可证。
