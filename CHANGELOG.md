# Changelog

---

## 2.2.1 · 2026-09-04

v2.2.1：面向公开目录发布的完善（无功能变更，缓存因脚本版本号变化自动失效一次）：
- **双语 description**：frontmatter `description` 改为英文为主 + 中文触发词兜底，兼顾 skills.sh / agentskill.sh 国际检索与中文 query 的激活精度。
- **英文 README**：`README.md` 改为英文（含与 anthropics/openai 官方 PDF 技能的差异对比、JSON 契约表、安全声明）；中文原文保留为 `README.zh-CN.md`。
- **LICENSE**：新增 MIT 许可证文件（此前仅在 frontmatter 声明）。
- **元数据补全**：新增 `compatibility` 与 `metadata`（author / version / tags），便于目录检索。
- **安全自查**：确认脚本无网络请求、无 subprocess、无 eval/exec、无遥测；6 处 `shutil.rmtree` 全部限定在自带缓存目录 `~/.cache/pdf-structured-extractor/` 内。

## 2.2.0 · 2026-09-04

v2.2.0：四项增强（对标同类 OCR/PDF 技能后落地）：
- **P0 MD 保真**：新增可选 `pymupdf4llm` 文本层（保留加粗/斜体/列表/表格语法），`--md-lib builtin|auto|pymupdf4llm`，默认不启用、未装自动回退内置逻辑（避免 57MB 版面模型依赖）。
- **P1 置信信号**：每页新增 `quality`（文字密度/表格/图片/疑似扫描/乱码/置信度）与 `page_class`（native/scanned/mixed）；顶层新增 `quality_warnings` 聚合提示。
- **P1 可选缓存**：基于 文件路径+大小+mtime+选项+脚本版本 的自动失效缓存（默认开启），支持 `--no-cache`/`--clear-cache`/`--clear-all-cache`/`--cache-stats`，结果含 `cache_hit`。
- **P2 分类+纯文本**：`page_class` 页面分类；新增 `--format text` 纯文本输出（`.txt`，去 Markdown 语法）。
- 校验：9/9 样本回归通过，stdout 仍纯净；新增字段均向后兼容。

## 2.1.1 · 2026-09-04

v2.1.1：跨客户端通用 PDF 结构化提取（WorkBuddy/Claude Code/Codex），扫描页走视觉，零 OCR 依赖。

