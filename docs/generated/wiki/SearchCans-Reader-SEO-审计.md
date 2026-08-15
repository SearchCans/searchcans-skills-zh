# SearchCans Reader SEO 审计

> 包含 canonical、H1、meta description、JSON-LD、文件和截图信号的提取报告

## 最适合的任务

网页转 Markdown、RAG 输入检查、动态页、PDF、Office 文件和页面级 SEO/GEO 审查。

## 使用的 SearchCans API

- Reader
- 文件提取
- 截图
- Account

## 账户感知行为

更高成本代理请求前自动预检；常规提取保持轻量。

## 调用示例

```text
使用 $searchcans-reader-seo-audit-zh 检查这个页面的提取效果和 SEO 信号。
```

请阅读可执行的 [SKILL.md](https://github.com/SearchCans/searchcans-skills-zh/tree/main/skills/searchcans-reader-seo-audit-zh)，了解可用参数、证据边界与报告要求。

## 解释边界

使用 SearchCans Reader API 提取 URL、PDF 或 Office 文档，并审计网页转 Markdown 的可提取性，以及 canonical URL、H1、meta description 和 JSON-LD 等 SEO 可观察 HTML 信号。适用于网页内容提取诊断、RAG 输入准备、动态页检查，或以成本感知 Reader 设置完成页面级 SEO/GEO 基础审计。
