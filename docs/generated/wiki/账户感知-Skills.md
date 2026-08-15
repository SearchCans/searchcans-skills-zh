# 账户感知 Skills

> 先估算范围、读取一次安全账户状态，再在超量任务开始前收缩或停止。

多请求 Skills 可使用 Account API 估算 SERP/Reader/文件成本、检查剩余积分和 Parallel Lane，并选择安全范围。报告只保留脱敏预算字段；永不包含邮箱、原始 Key 或凭据。

## 通用控制

- `--account-mode auto`：采用 Skill 的安全默认策略。
- `warn`：记录账户警告，但不修改请求范围。
- `enforce`：在业务请求前阻止预算不足任务。
- `cap`：在支持时收缩可变范围。
- `off`：明确跳过预检。

Reader 从代理档位 0 开始。更高档位改变成本，只应在确认访问问题后使用。

## Skill 行为

| Skill | 默认账户感知行为 |
| --- | --- |
| [SearchCans 中文深度研究](SearchCans-中文深度研究) | 一次预检，限制 Reader 来源数，并让并发不超过报告的 Parallel Lane。 |
| [SearchCans SERP 内容差距](SearchCans-SERP-内容差距) | 对多页任务预检，并在计划请求超出预算时限制页数。 |
| [SearchCans Reader SEO 审计](SearchCans-Reader-SEO-审计) | 更高成本代理请求前自动预检；常规提取保持轻量。 |
| [SearchCans 市场观察](SearchCans-市场观察) | 一次预检，限制新闻来源读取，并遵循报告的 Lane 数。 |
| [SearchCans 商品 SERP 简报](SearchCans-商品-SERP-简报) | 预估三次 SERP 与明确 Reader URL；需要时仅限制来源读取。 |
| [SearchCans 内容形式简报](SearchCans-内容形式-简报) | 为每个选定形式预检，并按固定优先级限制实际搜索面。 |
| [SearchCans RAG 来源策展](SearchCans-RAG-来源策展) | 预估搜索与 Reader/文件预算，限制来源数并让 worker 不超过 Lane 数。 |

被收缩的运行仅能得出其有效范围内的结论。始终报告请求与实际来源/页面/形式，绝不为跳过的工作编造发现。
