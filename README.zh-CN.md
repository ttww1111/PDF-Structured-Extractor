# pdf-structured-extractor

从 PDF 文档中**结构化提取**文字、表格与图片，保留标题层级和阅读顺序，支持双栏；扫描页 / 文字层乱码页自动渲染为 PNG，交由视觉能力识别回填。适用于“提取 PDF 文字”“PDF 转 Markdown”“导出 PDF 表格为 CSV/Markdown”“导出 PDF 图片”“识别扫描 PDF/扫描件”等场景。

> English version: [README.md](README.md)

## 特性

- **纯 Python**，唯一必需依赖 PyMuPDF（`pymupdf>=1.28.2`），跨平台
- **干净 JSON 契约**：脚本只向 stdout 输出单个纯净 JSON，诊断信息走 stderr，便于 agent 消费
- **扫描 / 乱码页走视觉能力**，零 OCR 重依赖（不装 Tesseract / RapidOCR）
- **图片内容级过滤**：按内容（SHA-256）去重，自动跳过整页背景图、横幅、纯色块（水印/logo/背景噪声）
- **可选更高保真 Markdown**：装了 `pymupdf4llm` 后通过 `--md-lib auto` 保留加粗/斜体/列表/表格语法（默认不启用，避免 57MB 版面模型依赖）
- **置信信号与页面分类**：每页 `quality`（文字密度/置信度）、`page_class`（native/scanned/mixed），顶层 `quality_warnings` 聚合提示
- **可选结果缓存**：默认开启，基于 文件+选项+版本 自动失效，重复提取直接复用；支持 `--no-cache` / `--clear-cache` / `--clear-all-cache` / `--cache-stats`
- **纯文本输出**：`--format text` 输出去 Markdown 语法的纯文本（`.txt`）
- **跨客户端通用**：WorkBuddy / Claude Code / Codex 直接复制即用，无客户端专属配置
- **可审计**：脚本无网络请求、无 subprocess、无遥测；删除操作仅作用于自带缓存目录 `~/.cache/pdf-structured-extractor/`

## 安装

把整个 `pdf-structured-extractor/` 文件夹复制到目标客户端的技能目录：

| 客户端 | 技能目录 |
| --- | --- |
| WorkBuddy | `~/.workbuddy/skills/pdf-structured-extractor/` |
| Claude Code | `~/.claude/skills/pdf-structured-extractor/` |
| Codex（OpenAI） | `~/.codex/skills/pdf-structured-extractor/`（若用 skills-manager，放入其源目录并建符号链接） |

安装依赖：

```bash
python3 -m pip install "pymupdf>=1.28.2"   # Linux / macOS（必需）
python  -m pip install "pymupdf>=1.28.2"   # Windows（若 python3 不存在）
# 可选：更高保真 Markdown（会额外下载约 57MB 版面模型，按需安装）
python3 -m pip install "pymupdf4llm>=1.28.2"
```

## 使用

将 `<skill_dir>` 替换为本 `SKILL.md` 所在目录：

```bash
python3 "<skill_dir>/scripts/extract_pdf.py" \
  "<PDF路径>" --output-dir "<输出目录>" \
  [--dpi 200] [--no-images] [--no-tables] [--no-links] \
  [--format markdown|text] [--md-lib builtin|auto|pymupdf4llm] \
  [--no-cache | --clear-cache | --clear-all-cache | --cache-stats]
```

脚本向 stdout 输出 JSON 结果（含 `markdown_path`、`document_info`、`pages`、`summary`、
`quality_warnings`、`cache_hit`），扫描页会渲染到 `scans/*.png`，由视觉能力识别后回填 Markdown。
详见 [SKILL.md](SKILL.md)。

## 不做什么

合并 / 拆分 / 加密 / 批注 / 去水印等任何 PDF 写回操作；本地 OCR；产品型号 / 价格等结构化业务字段（非普适，按需另写 skill）。

## 许可

[MIT](LICENSE)
