---
name: pdf-structured-extractor
description: >-
  Extract text, tables and images from PDF files into structured Markdown and CSV,
  preserving heading hierarchy and reading order. Handles two-column layouts;
  scanned and garbled pages are rendered to PNG for visual recognition instead of
  OCR (no Tesseract, no RapidOCR). Use when the user asks to extract PDF text,
  convert PDF to Markdown, export PDF tables to CSV, extract embedded images,
  or read a scanned PDF. 中文：从 PDF 结构化提取文字/表格/图片，保留标题层级与阅读顺序，支持双栏；
  扫描页与文字层乱码页自动渲染为 PNG 交视觉识别，零 OCR 依赖。适用于“提取 PDF 文字”“PDF 转 Markdown”
  “导出 PDF 表格为 CSV/Markdown”“导出 PDF 图片”“识别扫描 PDF/扫描件”。
dependency:
  python:
  - pymupdf>=1.28.2
author: Tony
slug: pdf-structured-extractor
displayName: PDF Structured Extractor
summary: 结构化提取 PDF 文字/表格/图片，扫描页走视觉识别，可选缓存与置信信号，跨客户端通用（WorkBuddy/Claude Code/Codex）。
license: MIT
compatibility: Requires Python 3.8+ and PyMuPDF >= 1.28.2. Works with any agent that can run shell commands.
metadata:
  author: Tony
  version: "2.2.4"
  tags: pdf pdf-extraction markdown table-extraction document-parsing pymupdf ocr-free
agent_created: true
version: 2.2.4
---

# PDF 结构化提取

## 与官方 / 同类技能的关系（去重说明，重要）

“PDF 文字/表格/图片提取”是红海能力，anthropics、openai、claude-office、guia-matthieu、
letta、redfox 等官方/社区技能都做，重叠严重。本技能**不假装通用提取独家**，而是定位为：

> **PDF 提取（agent 友好、零广告、扫描走视觉）**

与官方工具箱的差异：

- **anthropics/skills/pdf**：PDF 全家桶（提取 + 合并 + 拆分 + 表单 + 加密 + 水印 + OCR/tesseract），
  库栈重（pypdf/pdfplumber/reportlab + qpdf/pdftotext/pdftk）。它是读写全功能箱；本技能**纯提取**、零写回。
- **openai/skills/pdf**：偏“渲染 PNG 用视觉审阅版式 + reportlab 生成 PDF”。它重点是看/造 PDF；
  本技能重点是抽**结构化数据**供给 agent 消费。
- **本技能不可替代点**：① 干净 JSON 契约（agent 优先，fd 重定向保 stdout 纯净）② 扫描/乱码页走**视觉能力**、
  零 OCR 重依赖 ③ **零广告、零遥测**。

## 任务目标

- 从用户提供的本地 PDF 文件中**提取**（非改写）内容：
  - 文本层：标题/段落，按阅读顺序还原，支持双栏
  - 表格：导出为 Markdown（内联）与 CSV，并裁切表格区域存预览 PNG
  - 图片：按内容（SHA-256）去重导出，按覆盖面积/宽高比/信息量过滤装饰图，记录 bbox
  - 文档大纲(TOC) 与 超链接：提取为结构化字段
- 扫描页 / 乱码页（文字层不可信）：渲染为 PNG，交由视觉能力识别并回填
- 输出 Markdown 文件 + 同目录的图片/表格/扫描图，对话中给出简短摘要

## 适用范围与边界

**支持：**
- 文字版 PDF、双栏 PDF、含网格/无边框表格的 PDF、含嵌入图片的 PDF
- 纯扫描件 PDF、文字与扫描混合的 PDF
- 文字层乱码的 PDF（如可变字体导出导致复制乱码）：自动判为乱码页并交视觉识别

**不做（明确拒绝）：**
- 合并、拆分、旋转、加密、批注、去水印等任何 PDF 写入类操作
- 不调用本地 OCR（不依赖 Tesseract / RapidOCR）；扫描/乱码识别走视觉能力
- 不做 PDF 写回、不做 OCR（扫描仍走视觉能力）
- 不安装 Newton 等外部 PDF 技能

## 使用指引：parse once（解析一次，检索复用）

提取成本主要来自 PyMuPDF 解析。请遵循：

1. 运行脚本得到 `<文件名>.md` 后，**后续对该 PDF 的问答直接用 grep / 读取 .md**，
   不要为了“再找某段话”反复重跑脚本。
2. 需要表格原始数据用 `tables/*.csv`；
   需要视觉核对扫描页用 `scans/*.png`；需要核对表格版式用 `tables_preview/*.png`。

## 运行环境

- **唯一必需依赖**：Python 3.8+ 与 PyMuPDF ≥ 1.28.2（纯 Python，跨平台）。
- **可选依赖（更高保真 Markdown）**：`pymupdf4llm`（>=1.28.2）。它会额外拉入一个基于
  onnxruntime 的版面模型（约 57MB），因此**默认不安装、不启用**。仅当用户显式
  `pip install pymupdf4llm` 并通过 `--md-lib auto`（或 `pymupdf4llm`）选用时，文本层改用
  pymupdf4llm 生成，保留加粗/斜体/列表/表格的真实 Markdown 语法；未安装时自动回退内置逻辑。
- **安装依赖**（使用客户端自带的任意 Python，无需任何专属运行时）：
  ```bash
  python3 -m pip install "pymupdf>=1.28.2"   # Linux / macOS
  # Windows 上若 python3 不存在，改用 python
  python  -m pip install "pymupdf>=1.28.2"
  ```
- **脚本位置**：相对于本 `SKILL.md` 同级的 `scripts/extract_pdf.py`。
  各客户端加载技能后会提供本文件所在目录，请以该目录为基准解析脚本路径
  （例如 `<skill_dir>/scripts/extract_pdf.py`），**不要写死绝对路径**。
- **调用方式**：任何能执行 shell 命令的客户端，用其 Python 运行该脚本即可，
  与具体客户端（WorkBuddy / Claude Code / Codex 等）无关。

## 跨客户端安装（通用）

本技能是纯文件结构，把整个 `pdf-structured-extractor/` 文件夹复制到目标客户端的
技能目录即可，脚本不读取任何客户端配置，因此同一份文件在所有客户端行为一致：

| 客户端 | 技能目录 |
| --- | --- |
| WorkBuddy | `~/.workbuddy/skills/pdf-structured-extractor/` |
| Claude Code | `~/.claude/skills/pdf-structured-extractor/` |
| Codex（OpenAI） | `~/.codex/skills/pdf-structured-extractor/`（若用 skills-manager，放入其源目录并建符号链接） |

保持内部结构不变：

```text
pdf-structured-extractor/
├── SKILL.md
└── scripts/
    └── extract_pdf.py
```

> 本技能的 frontmatter 以 `name` + `description` 为跨客户端通用核心字段（Claude Code / WorkBuddy / Codex 均识别）；
> 其余元数据（`dependency`、`version`、`author` 等）为可选补充，不被识别的客户端会直接忽略，不影响功能，
> 因此同一份文件在所有客户端行为一致，无需为不同客户端维护多份。

## 操作步骤

### 1. 确认输入与输出目录

- 确认用户已提供**本地** PDF 路径（不支持仅给 URL，需先下载到本地）。
- 约定输出目录：与原文件同级的 `<原文件名>_extracted\`，例如
  `report.pdf` → `report_extracted\`。也可由用户指定。

### 2. 运行脚本

将 `<skill_dir>` 替换为本 SKILL.md 所在目录（各客户端加载技能后会提供该路径）。

```bash
python3 "<skill_dir>/scripts/extract_pdf.py" \
  "<PDF路径>" --output-dir "<输出目录>" \
  [--dpi 200] [--no-images] [--no-tables] [--no-links] \
  [--format markdown|text] [--md-lib builtin|auto|pymupdf4llm] \
  [--no-cache | --clear-cache | --clear-all-cache | --cache-stats]
```

> Windows 上若 `python3` 不存在，改用 `python`。脚本不依赖任何客户端专属运行时。

参数说明：

- `--dpi`：扫描/乱码页渲染分辨率（默认 200）
- `--no-images` / `--no-tables` / `--no-links`：分别关闭图片 / 表格 / 超链接提取
- `--format`：输出正文格式，`markdown`（默认，含标题/表格 Markdown）或 `text`（纯文本，去 Markdown 语法，文件后缀 `.txt`）
- `--md-lib`：文本层 Markdown 生成方式，`builtin`（默认，零额外依赖）/ `auto`（装了 pymupdf4llm 即用）/ `pymupdf4llm`（强制使用，未装则回退 builtin）
- 缓存（基于 文件路径+大小+mtime+选项+脚本版本 自动失效）：
  - 默认开启，命中时直接复用已提取的资源与 JSON，`result.cache_hit=true`
  - `--no-cache`：本次不读不写缓存
  - `--clear-cache`：清除当前 PDF 的缓存后重新提取
  - `--clear-all-cache` / `--cache-stats`：清空全部缓存 / 打印缓存目录、条目数与占用空间

### 3. 解析 JSON 结果

脚本只向 stdout 输出 JSON，诊断信息写 stderr（stdout 始终为单个纯净 JSON 对象）。
结构：

- 成功：`ok=true`，含 `markdown_path`、`document_info`、`pages`、`summary`、`quality_warnings`、`cache_hit`
  - `document_info.outline`：文档大纲（TOC）列表 `[层级, 标题, 页码]`
  - `summary.text_pages` / `scan_pages`：提取成功 / 需视觉识别的页码列表
  - `summary.link_count` / `table_count` / `image_count`
  - `quality_warnings`：跨页聚合的置信提示，如 `第3页: 疑似扫描件/无文字层，已渲染 PNG 待视觉识别`、`第1页: 文字密度偏低，提取结果可能不完整`
  - `cache_hit`：`true` 表示本次结果来自缓存
  - 每页 `text_status`：`extracted`（文字已提取）、`scan_required`
    （已渲染 PNG 待视觉识别）或 `error`（该页处理异常，见 `warnings`）
  - 每页 `page_class`：页面分类 `native`（正常文本页）/ `scanned`（需视觉识别）/ `mixed`（含图且文字偏少）
  - 每页 `quality`：质量信号 `{text_density, text_chars, has_table, has_image, suspected_scan, garbled, confidence}`，`confidence` 为 `high`/`medium`/`low`
  - 每页 `warnings`：如 `garbled_text_detected`（文字层疑似乱码）
  - 每页 `images[].bbox`：图片在页面中的坐标 `{x0,y0,x1,y1}`
  - 每页 `links`：超链接列表 `[{kind, uri?, page?}]`
- 失败：`ok=false`，含 `error.code`，可能为
  `FILE_NOT_FOUND` / `NOT_PDF` / `OPEN_FAILED` / `PASSWORD_REQUIRED` /
  `WRITE_FAILED` / `UNEXPECTED_ERROR` / `IMPORT_FAILED` / `ARG_MISSING`

### 4. 扫描页视觉回填（关键）

若 `summary.scan_pages` 非空：

- 对列表中每一页，读取对应 PNG：`扫描目录/pNNN.png`
- 使用视觉能力识别其中文字、标题、表格，**如实**回填到 Markdown 的
  `<!-- page:N -->` 区块
- 无法确认的内容标注“[识别不清]”，**不得臆造**
- 完成后在对话摘要中说明哪些页来自视觉识别

### 5. 交付

- 默认交付：`<输出目录>/<原文件名>.md` 文件 + 对话内摘要
- 摘要应包含：源文件、页数、文字页/扫描页、表格数、图片数、任何警告
- 图片/表格/扫描图位于同目录 `images\`、`tables\`、`scans\`，Markdown 用相对路径引用

## 输出目录结构

```text
<原文件名>_extracted\
├── <原文件名>.md          （正文 + 表格 + 图片引用）
├── images\                （按内容去重后的嵌入图片；已过滤整页背景/横幅/纯色块）
├── tables\                （每张表一个 UTF-8-SIG CSV）
├── tables_preview\        （表格区域裁切 PNG，供核对版式）
└── scans\                 （疑似扫描页/乱码页的 PNG，供视觉识别）
```

## 注意事项

- **隐私**：文件仅在本次提取中使用，不主动上传或存储到外部。
- **图片内容级过滤**：除尺寸过滤外，自动跳过①整页背景图（覆盖页面面积 ≥ 85%）②极端宽高比
  （长边/短边 ≥ 12，疑似横幅/分隔条）③大面积纯色块。目的：去掉水印/logo/背景噪声，
  保留真实前景图（晶体等产品图不受影响，因其面积小）。
- **乱码页判定**：当文字层出现 U+FFFD 替换符、或 Latin-1 mojibake 双字符（如 `Ã©` 代 `é`）、
  或 CJK 乱码特征（大量 Latin-1 组合符且无真实 CJK）时，判为乱码页并渲染 PNG 交视觉识别，
  不再吐垃圾文字。此举直击“可变字体导出复制乱码”的真实坑。
- **扫描/乱码识别**：视觉识别依赖图像清晰度，模糊页可能不完整；结果应声明“已尽力按视觉结构整理”。
- **复杂版式**：跨页表、嵌套表、极其不规则排版可能提取不佳，属已知限制。
- **文件大小**：建议 < 100MB；超大文件逐页处理，耗时较长。
- **加密 PDF**：需用户提供密码；脚本会返回 `PASSWORD_REQUIRED`，不尝试破解。

## 使用示例

**用户**：提取这个 PDF 的文字和表格 → `C:\data\catalog.pdf`

**处理**：
1. 运行脚本，`--output-dir C:\data\catalog_extracted`
2. 读取 JSON：10 页，其中第 3、7 页 `scan_required`
3. 读取 `scans/p003.png`、`scans/p007.png` 视觉识别并回填
4. 交付 `catalog_extracted\catalog.md` 与摘要
