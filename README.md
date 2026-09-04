# pdf-structured-extractor

从 PDF 文档中**结构化提取**文字、表格与图片，保留标题层级和阅读顺序，支持双栏；扫描页 / 文字层乱码页自动渲染为 PNG，交由视觉能力识别回填。适用于“提取 PDF 文字”“PDF 转 Markdown”“导出 PDF 表格为 CSV/Markdown”“导出 PDF 图片”“识别扫描 PDF/扫描件”等场景。

## 特性

- **纯 Python**，唯一依赖 PyMuPDF（`pymupdf>=1.28.2`），跨平台
- **干净 JSON 契约**：脚本只向 stdout 输出单个纯净 JSON，诊断信息走 stderr，便于 agent 消费
- **扫描 / 乱码页走视觉能力**，零 OCR 重依赖（不装 Tesseract / RapidOCR）
- **图片内容级过滤**：按内容（SHA-256）去重，自动跳过整页背景图、横幅、纯色块（水印/logo/背景噪声）
- **跨客户端通用**：WorkBuddy / Claude Code / Codex 直接复制即用，无客户端专属配置

## 安装

把整个 `pdf-structured-extractor/` 文件夹复制到目标客户端的技能目录：

| 客户端 | 技能目录 |
| --- | --- |
| WorkBuddy | `~/.workbuddy/skills/pdf-structured-extractor/` |
| Claude Code | `~/.claude/skills/pdf-structured-extractor/` |
| Codex（OpenAI） | `~/.codex/skills/pdf-structured-extractor/`（若用 skills-manager，放入其源目录并建符号链接） |

安装依赖：

```bash
python3 -m pip install "pymupdf>=1.28.2"   # Linux / macOS
python  -m pip install "pymupdf>=1.28.2"   # Windows（若 python3 不存在）
```

## 使用

将 `<skill_dir>` 替换为本 `SKILL.md` 所在目录：

```bash
python3 "<skill_dir>/scripts/extract_pdf.py" \
  "<PDF路径>" --output-dir "<输出目录>" \
  [--dpi 200] [--no-images] [--no-tables] [--no-links]
```

脚本向 stdout 输出 JSON 结果（含 `markdown_path`、`document_info`、`pages`、`summary`），
扫描页会渲染到 `scans/*.png`，由视觉能力识别后回填 Markdown。详见 [SKILL.md](SKILL.md)。

## 不做什么

合并 / 拆分 / 加密 / 批注 / 去水印等任何 PDF 写回操作；本地 OCR；产品型号 / 价格等结构化业务字段（非普适，按需另写 skill）。
