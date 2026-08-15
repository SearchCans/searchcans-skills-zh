# SearchCans 中文文档自动化

`docs/skills.json` 是 7 个公开中文 Skills 的唯一目录来源。生成器会验证它覆盖所有 `skills/*/SKILL.md`，然后更新 README 中的目录、生成的 Wiki 页面、静态 HTML 文档站和 sitemap。

## 新增或修改 Skill

1. 创建或修改 `skills/<name>/SKILL.md` 及其可执行资源。
2. 在 `docs/skills.json` 添加或更新匹配条目。
3. 运行 `python scripts/generate_docs.py`。
4. 运行 `python scripts/generate_docs.py --check` 与 `python -m unittest discover -s tests -v`。
5. 将 Skill、目录与生成内容一并提交。

不要手动编辑 `docs/generated/wiki/` 或 README 中自动生成的目录块；下次生成时会被覆盖。

## 一次性 GitHub 配置

1. 在仓库 **Settings → Pages** 中选择 **GitHub Actions** 作为发布源。后续符合条件的推送会由 `publish-docs.yml` 发布 `docs/site/`；Pages 使用 GitHub Actions 内置的 `GITHUB_TOKEN`，不依赖 Wiki 凭据。
2. 在 **Settings → Secrets and variables → Actions → Repository secrets** 中保存 `WIKI_SYNC_TOKEN`。使用英文库中已验证能推送 Wiki 的经典 Personal Access Token（`repo` scope）；它必须能够推送到 `https://github.com/SearchCans/searchcans-skills-zh.wiki.git`。当前 GitHub 组织配置下，刚才用于 Pages 的 Fine-grained PAT 会被该 Wiki Git 远程拒绝，因此不要把它用于此 Secret。
3. `sync-wiki.yml` 仅在 `main` 的文档/Skill 变化时运行，或从 **Actions → Run workflow** 手动运行。它先验证机密，再仅复制 `.searchcans-generated-pages` 列出的页面；不会递归清空未知的手工 Wiki 页面。

使用专用机器人或最小权限令牌。工作流通过一次性 `GIT_ASKPASS` 助手把令牌交给 Git，不会把它写入远程 URL、仓库、生成文档、Action 日志或面向用户的页面。
