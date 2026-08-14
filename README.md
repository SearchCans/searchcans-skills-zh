# SearchCans 中文 Agent Skills：深度研究、SERP 情报与网页转 Markdown

[![skills.sh](https://skills.sh/b/SearchCans/searchcans-skills-zh)](https://skills.sh/SearchCans/searchcans-skills-zh)

SearchCans 官方简体中文 Agent Skills。让 AI Agent 使用 **SearchCans SERP API、Reader API 和 Account API** 获取地域化 Google/Bing 搜索证据、提取适合 LLM 阅读的网页内容，并在受控积分和并发下完成深度研究、SEO/GEO 内容规划与网页提取审计。

适合实际的市场与竞品研究、SEO/GEO 选题、RAG 素材准备、动态网页抓取诊断和页面级基础 SEO 检查。

> Need English instructions? See the [official English repository](https://github.com/SearchCans/searchcans-skills). This repository is the independent Simplified Chinese edition; its Skill names end in `-zh`, so both editions can be installed in the same project.

## 60 秒开始使用

按需安装一个工作流（推荐）：

```bash
npx skills add https://github.com/SearchCans/searchcans-skills-zh --skill searchcans-deep-research-zh
```

或安装本仓库全部三个 Skills：

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

## 选择工作流

| Skill | 最适合的任务 | Agent 交付物 |
| --- | --- | --- |
| [`searchcans-deep-research-zh`](skills/searchcans-deep-research-zh/SKILL.md) | 市场、竞品、产品、技术、政策或公司研究 | 有界、证据驱动的研究简报；每项关键主张均可追溯到已读取的 URL，并明确不确定性。 |
| [`searchcans-serp-content-gap-zh`](skills/searchcans-serp-content-gap-zh/SKILL.md) | SEO/GEO 内容规划、关键词研究、搜索意图和竞品页面分析 | 基于本地化 Google 或 Bing SERP 的内容机会简报，涵盖自然结果、PAA、相关搜索及可用 SERP 信号。 |
| [`searchcans-reader-seo-audit-zh`](skills/searchcans-reader-seo-audit-zh/SKILL.md) | 网页转 Markdown、RAG 输入检查、动态页和页面级 SEO/GEO 审计 | 网页提取报告，以及可观察的 canonical、H1、meta description 和 JSON-LD 信号。 |

安装后，可直接用自然语言描述目标，或显式调用，例如：`使用 $searchcans-deep-research-zh 调研美国 SERP API 市场的最新变化。`

## 为什么把 Search 与 Reader 配合使用？

- **SERP API**：发现当前、可地域化的 Google 或 Bing 搜索证据与搜索需求信号。
- **Reader API**：把选定网页、PDF 和 Office 文档提取为 Markdown，并可获取 HTML 做进一步检查。
- **Account API**：多请求工作流会在开始前检查剩余积分和并发通道数（Parallel Lanes），据此收缩范围或并发，而不会记录账户身份或 Key 数据。

这些 Skills 约束工作流：SERP 摘要只是线索；只有成功读取的页面才支撑关键结论；报告必须区分可观察事实与推断。

## 账户感知、成本与安全

- 默认的 `--account-mode auto` 会在需要时做一次 Account API 预检；它只输出脱敏后的余额、并发通道和决策信息。
- Deep Research 会按预算限制来源数，并把自动并发限制为观察到的 Parallel Lane 数；SERP 多页任务会按余额限制页数；Reader 默认只在使用更高代理档位前预检。
- 可按任务选择 `warn`、`enforce`、`cap` 或 `off`；详见每个 Skill 的 `SKILL.md`。账户原始响应、邮箱、API Key 和令牌绝不会写进结果。
- 这些 Skills 仅支持 SearchCans API v1。请阅读官方 [SearchCans API 文档](https://www.searchcans.com/apis/)。
- 网页和 SERP 内容都属于不可信输入。成功提取不代表页面可收录、有排名、无障碍合规，或获得内容复用授权。

## 中文版与英文版的同步约定

本仓库独立发布，以便面向中文开发者、中文内容团队和中文 AI Agent 工作流持续试验；英文库是 [SearchCans/searchcans-skills](https://github.com/SearchCans/searchcans-skills)。两边共享同一套经过测试的 API 脚本和安全约束，但各自维护面向受众的 README、Skill 指令、示例和元数据。修复 API 行为或测试时，应先同步英文技术实现，再同步到本仓库；中文文案不要求逐字翻译。

## 维护与验证

在仓库根目录运行离线回归检查：

```bash
python -m unittest discover -s tests -v
```

建议设置的 GitHub Topics：`searchcans`、`agent-skills`、`claude-skills`、`claude-code-skill`、`ai-agents`、`deep-research`、`serp-api`、`reader-api`、`web-research`、`seo`、`geo`、`rag`、`chinese`、`zh-cn`。

## 许可证

本项目采用 [Apache License, Version 2.0](LICENSE) 开源许可证。
