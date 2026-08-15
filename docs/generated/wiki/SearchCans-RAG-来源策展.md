# SearchCans RAG 来源策展

> 小规模、域名多样且经过 Reader/文件提取验证的来源清单

## 最适合的任务

Grounding Pack、来源策展、知识库入库和预入库证据检查。

## 使用的 SearchCans API

- Google 或 Bing 搜索
- Reader
- 文件提取
- 截图
- Account

## 账户感知行为

预估搜索与 Reader/文件预算，限制来源数并让 worker 不超过 Lane 数。

## 调用示例

```text
使用 $searchcans-rag-source-curator-zh 为这个 RAG 问题策展可作为证据的来源。
```

请阅读可执行的 [SKILL.md](https://github.com/SearchCans/searchcans-skills-zh/tree/main/skills/searchcans-rag-source-curator-zh)，了解可用参数、证据边界与报告要求。

## 解释边界

使用 SearchCans 的地域化 Google 或 Bing 搜索、Reader 提取、文件提取和可选页面截图创建小规模、多样、可作为证据的 RAG 来源清单。适用于 grounding pack、来源策展、知识库入库和预入库证据检查。
