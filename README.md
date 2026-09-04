# pdf-structured-extractor

Extract text, tables and images from PDF files into structured Markdown and CSV — heading hierarchy and reading order preserved, two-column layouts handled, scanned and garbled pages rendered to PNG for visual recognition instead of OCR.

> 中文文档：[README.zh-CN.md](README.zh-CN.md)

## Why another PDF skill

PDF extraction is a crowded space — `anthropics/skills`, `openai/skills`, `claude-office` and several community skills all do it. This one is deliberately narrower:

| | anthropics/skills `pdf` | openai/skills `pdf` | **this skill** |
| --- | --- | --- | --- |
| Scope | Full toolbox: extract, merge, split, forms, encrypt, watermark, OCR | Render to PNG for visual review, generate PDFs with reportlab | **Extraction only** |
| Dependencies | pypdf, pdfplumber, reportlab, qpdf, pdftotext, pdftk | reportlab + rendering | **PyMuPDF only** |
| Output | Mixed | Visual / generated PDF | **Clean JSON contract for agents** |
| Scanned pages | Tesseract OCR | Visual review | **Rendered PNG, filled in by the agent's vision** |

Three things this skill does that the others don't:

1. **Clean JSON contract.** A single JSON object goes to stdout, diagnostics go to stderr. Nothing else pollutes the stream, so an agent can parse it directly.
2. **No OCR stack.** Scanned pages and garbled text layers are detected automatically and rendered to PNG for the agent's own vision capability. No Tesseract, no RapidOCR, no model downloads.
3. **No telemetry, no ads, no network calls.** See [Privacy & security](#privacy--security).

## Features

- **Pure Python, one dependency.** PyMuPDF `>=1.28.2`, cross-platform.
- **Reading order and heading hierarchy** preserved, including two-column layouts.
- **Tables** exported as Markdown (inline) and UTF-8-SIG CSV, plus a cropped PNG of each table region for layout verification.
- **Images** deduplicated by SHA-256 of content, with bounding boxes recorded. Decorative images are filtered out: full-page backgrounds (≥85% coverage), extreme aspect ratios (≥12:1), and large flat colour blocks — so watermarks, logos and background noise are dropped while real content images survive.
- **Quality signals per page.** `quality` (text density, char count, table/image flags, suspected scan, garbled flag, confidence) and `page_class` (`native` / `scanned` / `mixed`), aggregated into a top-level `quality_warnings` list.
- **Optional result cache.** On by default, invalidated by file path + size + mtime + options + script version.
- **Garbled text detection.** Pages with U+FFFD replacement characters, Latin-1 mojibake or CJK corruption signatures are treated as unreadable and routed to vision instead of emitting garbage text.
- **Optional higher-fidelity Markdown.** With `pymupdf4llm` installed, `--md-lib auto` keeps real bold / italic / list / table syntax. Off by default to avoid pulling a ~57MB layout model.
- **Plain text output.** `--format text` strips Markdown syntax and writes `.txt`.
- **Client-agnostic.** Works in WorkBuddy, Claude Code, Codex, or anywhere you can run a shell command.

## Install

```bash
npx skills add ttww1111/pdf-structured-extractor
```

Or copy the folder into your client's skills directory:

| Client | Skills directory |
| --- | --- |
| WorkBuddy | `~/.workbuddy/skills/pdf-structured-extractor/` |
| Claude Code | `~/.claude/skills/pdf-structured-extractor/` |
| Codex | `~/.codex/skills/pdf-structured-extractor/` |

Then install the dependency:

```bash
python3 -m pip install "pymupdf>=1.28.2"   # Linux / macOS
python  -m pip install "pymupdf>=1.28.2"   # Windows

# Optional: higher-fidelity Markdown (downloads a ~57MB layout model)
python3 -m pip install "pymupdf4llm>=1.28.2"
```

## Usage

Replace `<skill_dir>` with the directory containing `SKILL.md`:

```bash
python3 "<skill_dir>/scripts/extract_pdf.py" \
  "<path/to/file.pdf>" --output-dir "<path/to/output>" \
  [--dpi 200] [--no-images] [--no-tables] [--no-links] \
  [--format markdown|text] [--md-lib builtin|auto|pymupdf4llm] \
  [--no-cache | --clear-cache | --clear-all-cache | --cache-stats]
```

| Flag | Meaning |
| --- | --- |
| `--dpi` | Render resolution for scanned / garbled pages (default 200) |
| `--no-images` / `--no-tables` / `--no-links` | Skip image / table / link extraction |
| `--format` | `markdown` (default) or `text` (plain text, writes `.txt`) |
| `--md-lib` | `builtin` (default, zero extra deps) / `auto` (use pymupdf4llm if present) / `pymupdf4llm` (force, falls back if missing) |
| `--no-cache` | Bypass cache for this run |
| `--clear-cache` | Drop this PDF's cache entry and re-extract |
| `--clear-all-cache` / `--cache-stats` | Wipe the whole cache / report cache location, entry count and size |

Use `python` instead of `python3` on Windows if needed.

### Scanned pages

If `summary.scan_pages` is non-empty, read the matching `scans/pNNN.png` files with your vision capability and fill the content back into the `<!-- page:N -->` block of the Markdown. Mark anything you cannot confirm as `[illegible]` rather than guessing.

## Output layout

```text
<name>_extracted/
├── <name>.md            # body text, tables, image references
├── images/              # deduplicated embedded images
├── tables/              # one UTF-8-SIG CSV per table
├── tables_preview/      # cropped PNG of each table region
└── scans/               # PNG of scanned / garbled pages, for vision
```

Markdown references images with relative paths, so the whole folder can be moved or zipped as-is.

## JSON contract

On success (`ok=true`), stdout carries:

| Field | Contents |
| --- | --- |
| `markdown_path` | Path to the generated file |
| `document_info.outline` | Document TOC as `[level, title, page]` |
| `pages[].text_status` | `extracted` / `scan_required` / `error` |
| `pages[].page_class` | `native` / `scanned` / `mixed` |
| `pages[].quality` | `text_density`, `text_chars`, `has_table`, `has_image`, `suspected_scan`, `garbled`, `confidence` |
| `pages[].warnings` | e.g. `garbled_text_detected` |
| `pages[].images[].bbox` | `{x0, y0, x1, y1}` |
| `pages[].links` | `[{kind, uri?, page?}]` |
| `summary` | `scan_pages`, `link_count`, `table_count`, `image_count` |
| `quality_warnings` | Aggregated cross-page confidence notes |
| `cache_hit` | `true` if the result came from cache |

On failure (`ok=false`), `error.code` is one of `FILE_NOT_FOUND`, `NOT_PDF`, `OPEN_FAILED`, `PASSWORD_REQUIRED`, `WRITE_FAILED`, `IMPORT_FAILED`, `ARG_MISSING`, `UNEXPECTED_ERROR`.

## Privacy & security

- Files are processed locally. Nothing is uploaded anywhere.
- The script makes **no network calls**, spawns **no subprocesses**, and sends **no telemetry**. It imports only the standard library plus PyMuPDF.
- The only deletion the script performs is inside its own cache directory, `~/.cache/pdf-structured-extractor/`. It never deletes or overwrites anything in your output directory beyond the files it writes.
- Encrypted PDFs return `PASSWORD_REQUIRED`; the script never attempts to crack them.

## Limitations

- No PDF writing: no merge, split, rotate, encrypt, annotate or watermark.
- No local OCR — that is intentional, scanned pages go through vision instead.
- Cross-page tables, nested tables and highly irregular layouts may extract poorly.
- Files under 100MB are recommended; very large documents are processed page by page and take longer.

## License

[MIT](LICENSE)
