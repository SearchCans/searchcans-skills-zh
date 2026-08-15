#!/usr/bin/env python3
"""从一个中文 Skill 目录生成 README、Wiki 与静态文档站。"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs" / "skills.json"
WIKI_DIR = ROOT / "docs" / "generated" / "wiki"
SITE_DIR = ROOT / "docs" / "site"
START = "<!-- BEGIN GENERATED:SKILL-CATALOG -->"
END = "<!-- END GENERATED:SKILL-CATALOG -->"


def load_catalog() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or not isinstance(raw.get("site"), dict) or not isinstance(raw.get("skills"), list):
        raise ValueError("docs/skills.json 必须使用 schema_version 1，并包含 site 和 skills")
    required = {"name", "title", "page", "category", "best_for", "delivers", "apis", "account_policy", "example"}
    skills = raw["skills"]
    names = [item.get("name") for item in skills if isinstance(item, dict)]
    if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ValueError("Skill 名称必须是唯一字符串")
    if any(not isinstance(item, dict) or required - set(item) or not isinstance(item["apis"], list) for item in skills):
        raise ValueError("每个目录条目必须包含全部字段")
    return raw["site"], skills


def skill_metadata(name: str) -> dict[str, str]:
    path = ROOT / "skills" / name / "SKILL.md"
    if not path.is_file():
        raise ValueError(f"目录引用了不存在的 Skill：{name}")
    content = path.read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not frontmatter:
        raise ValueError(f"缺少 frontmatter：{path}")
    fields = dict(re.findall(r"^(name|description):\s*(.+)$", frontmatter.group(1), re.MULTILINE))
    if fields.get("name") != name or not fields.get("description"):
        raise ValueError(f"Skill frontmatter 无效：{path}")
    return fields


def validate_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    folders = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    names = {item["name"] for item in catalog}
    if folders != names:
        raise ValueError(f"目录与 Skills 不匹配；缺少={sorted(folders - names)}，多余={sorted(names - folders)}")
    return [{**item, "description": skill_metadata(item["name"])["description"]} for item in catalog]


def markdown_catalog(skills: list[dict[str, Any]]) -> str:
    rows = ["| Skill | 最适合的任务 | Agent 交付物 |", "| --- | --- | --- |"]
    rows.extend(f"| [`{item['name']}`](skills/{item['name']}/SKILL.md) | {item['best_for']} | {item['delivers']} |" for item in skills)
    return "\n".join(rows)


def replace_readme(catalog: str) -> str:
    path = ROOT / "README.md"
    current = path.read_text(encoding="utf-8")
    if START not in current or END not in current:
        raise ValueError("README.md 缺少自动生成目录标记")
    return re.sub(re.escape(START) + r".*?" + re.escape(END), f"{START}\n{catalog}\n{END}", current, flags=re.DOTALL)


def wiki_home(skills: list[dict[str, Any]]) -> str:
    rows = ["| 你的目标 | 从这里开始 |", "| --- | --- |"]
    rows.extend(f"| {item['best_for']} | [{item['title']}]({item['page']}) |" for item in skills)
    return "\n".join([
        "# SearchCans 中文 Agent Skills", "", "> 用当前、地域化的搜索证据和干净网页内容，完成可审计的 AI 工作。", "",
        "SearchCans Skills 将 SERP 发现与 Reader、文件提取、截图和 Account API 控制组合在一起。所有多请求任务均限制来源范围，并记录实际获取到了什么。", "",
        "## 60 秒开始", "", "```bash", "npx skills add SearchCans/searchcans-skills-zh", "```", "",
        "只安装一个 Skill：", "", "```bash", "npx skills add https://github.com/SearchCans/searchcans-skills-zh --skill searchcans-deep-research-zh", "```", "",
        "仅在执行环境中设置 `SEARCHCANS_API_KEY`，不得写入提示词、报告、源码或 Git 提交。", "",
        "> **每周免费积分：** 登录后打开 [Dashboard → Free Redemption Codes](https://www.searchcans.com/dashboard/redeem-codes/)，领取本周兑换码。每周发布新码；每个兑换码可兑换 **1,000 API 积分**，每个账户每批可兑换一次。", "",
        "## 选择一个 Skill", "", *rows, "",
        "## 文档", "", "- [快速开始](快速开始)", "- [选择 Skills](选择-Skills)", "- [账户感知 Skills](账户感知-Skills)", "- [深度研究 Workflow](深度研究-Workflow)", "- [故障排查](故障排查)", "",
        "[查看 API 文档](https://www.searchcans.com/apis/) · [查看源码](https://github.com/SearchCans/searchcans-skills-zh)"
    ]) + "\n"


def wiki_start(skills: list[dict[str, Any]]) -> str:
    available = "\n".join(f"- [{item['title']}]({item['page']})：{item['best_for']}" for item in skills)
    return f"""# 快速开始

SearchCans Skills 将当前 SERP 观察和选定网页提取转为有界、可追溯的 Agent 工作。

## 安装

```bash
npx skills add SearchCans/searchcans-skills-zh
```

按需使用 `--skill <name>` 安装单个 Skill。在执行环境中设置 `SEARCHCANS_API_KEY`，不要写入源码或提示词。

## 当前可用 Skills

{available}

## 负责任地开始

目标市场重要时，同时指定 `country` 与 `language`。从能回答问题的最小来源/结果预算开始。解释前先检查状态：`ok` 是已观察结果，`capped` 是部分结果，`blocked` 表示业务请求未执行，Reader 的 `empty`/`error` 来源不能支撑主张。
"""


def wiki_choose(skills: list[dict[str, Any]]) -> str:
    rows = ["| 目标 | Skill | 原因 |", "| --- | --- | --- |"]
    rows.extend(f"| {item['best_for']} | [{item['title']}]({item['page']}) | {item['delivers']} |" for item in skills)
    return "\n".join([
        "# 选择 Skills", "", "选择能产生所需证据或产物的最小 Skill。仅当上一个产物成为下一个 Skill 的有界输入时，再组合使用。", "", *rows, "",
        "## 选择规则", "", "- 需要多来源、3–5 个子问题和正式证据门槛时，用 **中文深度研究**。", "- 一个地域化关键词/SERP 决策用 **SERP 内容差距**；决策涉及图片、视频和短视频形式时，用 **内容形式简报**。", "- 已知单个 URL 或文件用 **Reader SEO 审计**；先发现并选择少量来源，再入库时用 **RAG 来源策展**。", "- 可重复的市场/新闻快照用 **市场观察**；特定市场的商品与商家观察用 **商品 SERP 简报**。", "", "SERP 摘要和结果展示不是证据。重要主张前必须读取相应页面。"
    ]) + "\n"


def wiki_account(skills: list[dict[str, Any]]) -> str:
    rows = ["| Skill | 默认账户感知行为 |", "| --- | --- |"]
    rows.extend(f"| [{item['title']}]({item['page']}) | {item['account_policy']} |" for item in skills)
    return "\n".join([
        "# 账户感知 Skills", "", "> 先估算范围、读取一次安全账户状态，再在超量任务开始前收缩或停止。", "",
        "多请求 Skills 可使用 Account API 估算 SERP/Reader/文件成本、检查剩余积分和 Parallel Lane，并选择安全范围。报告只保留脱敏预算字段；永不包含邮箱、原始 Key 或凭据。", "",
        "## 通用控制", "", "- `--account-mode auto`：采用 Skill 的安全默认策略。", "- `warn`：记录账户警告，但不修改请求范围。", "- `enforce`：在业务请求前阻止预算不足任务。", "- `cap`：在支持时收缩可变范围。", "- `off`：明确跳过预检。", "", "Reader 从代理档位 0 开始。更高档位改变成本，只应在确认访问问题后使用。", "",
        "## Skill 行为", "", *rows, "", "被收缩的运行仅能得出其有效范围内的结论。始终报告请求与实际来源/页面/形式，绝不为跳过的工作编造发现。"
    ]) + "\n"


def wiki_research() -> str:
    return """# 深度研究 Workflow

> 使用当前网页证据回答已定义的问题，不能把 SERP 摘要误写为证明。

## 搜索前规划

写出 3–5 个互不重复的子问题，覆盖中心主张、一手证据、替代观点、重要异议与决策影响。明确国家/语言市场、来源预算和时效要求。

## 搜索、选择、读取

搜索每个子问题，选择小而域名多样的来源集合，再用 Reader 读取页面。重要主张仅可使用成功提取后的 `claim_eligible_urls`。

## 如实报告

交付结论、支撑 URL、冲突证据、不确定性、方法，以及请求与实际预算。结果可以很新，但不代表穷尽；说明没有检查什么。

使用 [SearchCans 中文深度研究](SearchCans-中文深度研究) 执行该 Workflow。
"""


def wiki_troubleshooting() -> str:
    return """# 故障排查

不要在 Issue、截图或日志中包含 API Key、账户邮箱、令牌或原始 Account API 响应。

## 找不到 `SEARCHCANS_API_KEY`

在同一个执行环境设置 Key 后重新运行。不要将 Key 加入 `SKILL.md`、JSON 输出或仓库文件。

## 任务被 `blocked` 或 `capped`

读取 `account_guard`、请求限制与实际限制。`blocked` 表示业务请求未执行；`capped` 表示只执行了记录的有效范围。不得对跳过的来源、页面或形式作结论。

## Reader 提取 `empty` 或 `error`

将页面视为未读取。检查 URL；对已知 JavaScript 页面使用 `--headless`；仅在有理由时提高代理档位。空 Reader 结果不是证据。

## 结果在不同运行或引擎间不一致

SERP 对时间和地域敏感。记录查询、国家、语言、引擎、检索时间与限制；将快照比较为观察，不是排名保证。

## 需要帮助

提交 Issue 时，附上 Skill 名称、脱敏状态/请求元数据、市场、去除凭据的命令参数，以及预期和实际行为。
"""


def wiki_skill(item: dict[str, Any]) -> str:
    apis = "\n".join(f"- {api}" for api in item["apis"])
    return f"""# {item['title']}

> {item['delivers']}

## 最适合的任务

{item['best_for']}。

## 使用的 SearchCans API

{apis}

## 账户感知行为

{item['account_policy']}

## 调用示例

```text
{item['example']}
```

请阅读可执行的 [SKILL.md](https://github.com/SearchCans/searchcans-skills-zh/tree/main/skills/{item['name']})，了解可用参数、证据边界与报告要求。

## 解释边界

{item['description']}
"""


def wiki_sidebar(skills: list[dict[str, Any]]) -> str:
    lines = ["## SearchCans 中文 Skills", "", "- [首页](Home)", "- [快速开始](快速开始)", "- [选择 Skills](选择-Skills)", "- [账户感知 Skills](账户感知-Skills)", "- [深度研究 Workflow](深度研究-Workflow)", "- [故障排查](故障排查)", "", "## Skills"]
    lines.extend(f"- [{item['title']}]({item['page']})" for item in skills)
    return "\n".join(lines) + "\n"


def html_shell(site: dict[str, Any], title: str, description: str, body: str) -> str:
    base = site["base_url"].rstrip("/")
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title><meta name=\"description\" content=\"{html.escape(description)}\"><style>body{{font-family:ui-sans-serif,system-ui,sans-serif;max-width:920px;margin:0 auto;padding:32px;color:#18212f;line-height:1.7}}a{{color:#1265d6}}header{{border-bottom:1px solid #dde3ea;margin-bottom:32px}}nav a{{margin-right:16px}}.tag{{display:inline-block;background:#edf5ff;border-radius:999px;padding:3px 10px;margin:3px;font-size:.86rem}}article{{border:1px solid #e4e8ed;border-radius:12px;padding:22px;margin:18px 0}}</style></head><body><header><h1><a href=\"{base}/\">SearchCans 中文 Agent Skills</a></h1><nav><a href=\"{base}/\">首页</a><a href=\"{base}/skills/\">全部 Skills</a><a href=\"{site['repository_url']}\">GitHub</a></nav></header>{body}</body></html>
"""


def site_index(site: dict[str, Any], skills: list[dict[str, Any]]) -> str:
    cards = "".join(f"<article><h2><a href=\"skills/{item['name']}/\">{html.escape(item['title'])}</a></h2><p>{html.escape(item['delivers'])}</p><p><strong>最适合：</strong>{html.escape(item['best_for'])}</p></article>" for item in skills)
    return html_shell(site, site["title"], site["description"], f"<main><p>{html.escape(site['description'])}</p><p>安装：<code>npx skills add SearchCans/searchcans-skills-zh</code></p>{cards}</main>")


def site_skill(site: dict[str, Any], item: dict[str, Any]) -> str:
    tags = "".join(f"<span class=\"tag\">{html.escape(api)}</span>" for api in item["apis"])
    body = f"<main><h2>{html.escape(item['title'])}</h2><p>{html.escape(item['description'])}</p><h3>最适合</h3><p>{html.escape(item['best_for'])}</p><h3>交付物</h3><p>{html.escape(item['delivers'])}</p><h3>API</h3>{tags}<h3>账户感知</h3><p>{html.escape(item['account_policy'])}</p><p><a href=\"{site['repository_url']}/tree/main/skills/{item['name']}\">在 GitHub 打开这个 Skill</a></p></main>"
    return html_shell(site, item["title"], item["description"], body)


def outputs(site: dict[str, Any], skills: list[dict[str, Any]]) -> dict[Path, str]:
    files: dict[Path, str] = {ROOT / "README.md": replace_readme(markdown_catalog(skills))}
    pages = {
        "Home.md": wiki_home(skills),
        "主页.md": "# 主页\n\n请从 [首页](Home) 开始。\n",
        "快速开始.md": wiki_start(skills),
        "选择-Skills.md": wiki_choose(skills),
        "账户感知-Skills.md": wiki_account(skills),
        "深度研究-Workflow.md": wiki_research(),
        "故障排查.md": wiki_troubleshooting(),
        "_Sidebar.md": wiki_sidebar(skills),
    }
    pages.update({f"{item['page']}.md": wiki_skill(item) for item in skills})
    pages[".searchcans-generated-pages"] = "\n".join(sorted(name for name in pages if name.endswith(".md"))) + "\n"
    files.update({WIKI_DIR / name: content for name, content in pages.items()})
    files[SITE_DIR / ".nojekyll"] = ""
    files[SITE_DIR / "index.html"] = site_index(site, skills)
    files[SITE_DIR / "skills" / "index.html"] = site_index(site, skills)
    for item in skills:
        files[SITE_DIR / "skills" / item["name"] / "index.html"] = site_skill(site, item)
    base = site["base_url"].rstrip("/")
    urls = [f"{base}/", f"{base}/skills/"] + [f"{base}/skills/{item['name']}/" for item in skills]
    files[SITE_DIR / "sitemap.xml"] = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "".join(f"  <url><loc>{url}</loc></url>\n" for url in urls) + "</urlset>\n"
    files[SITE_DIR / "robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    return files


def write_files(files: dict[Path, str], check: bool) -> list[Path]:
    changed: list[Path] = []
    for path, content in files.items():
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        if existing != content:
            changed.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="如果自动生成文档不是最新版本则失败。")
    args = parser.parse_args()
    site, catalog = load_catalog()
    skills = validate_catalog(catalog)
    changed = write_files(outputs(site, skills), args.check)
    if args.check and changed:
        print("自动生成文档已过期：")
        print("\n".join(str(path.relative_to(ROOT)) for path in changed))
        return 1
    print(f"已为 {len(skills)} 个 Skills {'验证' if args.check else '生成'}文档。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
