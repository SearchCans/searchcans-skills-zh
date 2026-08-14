# 审计结果解读

## 信号边界

- 未返回 HTML 只代表 canonical、H1、meta description 和 JSON-LD 结果不可用，不代表它们一定缺失。
- Reader Markdown 长度只衡量可提取性，不衡量内容质量、流量或排名。
- canonical URL、H1 或 JSON-LD 是可观察信号。最终实现应在页面源代码和相关搜索工具中验证。

## 排查顺序

1. 评估内容前，先解决提取失败或为空的问题。
2. 仅对依赖 JavaScript 的页面使用无头渲染。
3. 从代理档位 0 开始，首个可用档位即停止升级。
4. 将无效 JSON-LD 与缺少 JSON-LD 分开报告。
5. 文档提取是文件内容检查，不是 HTML SEO 审计。
