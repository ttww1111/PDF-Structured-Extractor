#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 结构化提取脚本。

只做提取，不做任何写回 PDF 的操作：
  - 文本层：标题/段落按阅读顺序与多栏重排
  - 表格：find_tables 两策略，输出 Markdown 内联 + CSV + 表格预览图
  - 图片：按内容去重导出，按覆盖面积/宽高比/信息量过滤装饰图
  - 扫描页 / 乱码页：渲染 PNG，交 Agent 视觉识别
  - 文档大纲(TOC) 与 超链接 提取

stdout 只输出 JSON，诊断信息写 stderr。
"""

import sys
import os
import csv
import json
import hashlib
import io
import statistics
import argparse
from pathlib import Path

# ---- stdout 纯净度保护 -------------------------------------------------
# PyMuPDF 在 import 期与部分 API 调用期（如 find_tables）会绕过 sys.stdout，
# 直接写 fd 1，污染本脚本约定“stdout 只输出 JSON”的契约。解决方案：
#   1) 全程把 fd 1 重定向到 stderr（fd 2），任何 PyMuPDF 提示都落在 stderr；
#   2) 仅在 emit() 把最终 JSON 写到“保存下来的真实 stdout fd”（_fd1），
#      该 fd 不受 fd 1 重定向影响，保证 stdout 干净。
_fd1 = os.dup(1)
os.dup2(2, 1)


def _emit(obj):
    """把最终 JSON 写到真实 stdout（_fd1），绕过被重定向的 fd 1。"""
    payload = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    view = memoryview(payload)
    while view:
        n = os.write(_fd1, view)
        view = view[n:]


def _fail(code, message):
    _emit({"ok": False, "error": {"code": code, "message": message}, "pages": []})
    sys.exit(1)


try:
    import fitz  # PyMuPDF
except ImportError:
    _fail("IMPORT_FAILED", "缺少依赖 pymupdf，请安装：pip install \"pymupdf>=1.28.2\"")


# ---------- 阈值常量 ----------
SCAN_TEXT_THRESHOLD = 3     # 文字层字符数低于此值且含图片 → 判定为扫描页（疑似无文字层）
MIN_IMG_SIDE = 16           # 忽略小于该像素的图片（噪点/图标）
MIN_IMG_AREA = 1024
SCAN_DPI = 200              # 扫描页/乱码页渲染分辨率
PAGE_SEP_GAP_RATIO = 1.5    # 行间距超过该行高 * 此值则视为新段落
# 图片内容级过滤
BG_COVERAGE = 0.85          # 单图覆盖页面面积比例超过此值 → 视作整页背景，跳过
MAX_ASPECT_RATIO = 12.0     # 宽高比（长边/短边）超过此值 → 横幅/分隔条，跳过
SOLID_COVERAGE = 0.5        # 覆盖比例 ≥ 此值且唯一颜色极少 → 纯色块，跳过
SOLID_UNIQUE_COLORS = 2     # 唯一颜色数 ≤ 此值且面积足够大 → 纯色块


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rect_area(r):
    """计算 Rect 面积（本版本 fitz.Rect 无 .area 属性，故显式计算）。"""
    try:
        return (r.x1 - r.x0) * (r.y1 - r.y0)
    except Exception:
        return 0.0


# ----------------------------------------------------------------------
# 文本行收集与版式分析
# ----------------------------------------------------------------------

def collect_lines(page):
    """从页面收集文本行，返回 dict 列表。

    每条含 y0, y1, x0, x1, text, size, bold, block_no。
    保留 span 原文，不在 span 层强制拼接空格。
    """
    lines = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            sizes = [s.get("size", 0) for s in spans if s.get("size")]
            size = statistics.median(sizes) if sizes else 0
            bold = any("bold" in (s.get("font", "") or "").lower() for s in spans)
            bbox = line.get("bbox", [0, 0, 0, 0])
            lines.append({
                "y0": bbox[1], "y1": bbox[3], "x0": bbox[0], "x1": bbox[2],
                "text": text.strip(), "size": size, "bold": bold,
            })
    return lines


def body_size_of(lines):
    """用行字号中位数估计正文字号，过滤异常值。"""
    sizes = [ln["size"] for ln in lines if 4 <= ln["size"] <= 120]
    if not sizes:
        return 10.0
    return statistics.median(sizes)


def detect_columns(lines, page_width):
    """返回 (is_multi, col_index_fn)。双栏时按列顺序输出。"""
    if not lines:
        return False, lambda ln: 0
    right = [ln for ln in lines if ln["x0"] >= page_width * 0.55]
    if len(right) >= max(3, len(lines) * 0.2):
        mid = page_width / 2

        def col(ln):
            return 1 if ln["x0"] >= mid else 0
        return True, col
    return False, lambda ln: 0


def order_lines(lines, page_width):
    """按阅读顺序排序：多栏先左列从上到下，再右列。"""
    is_multi, col_fn = detect_columns(lines, page_width)
    keyed = sorted(
        enumerate(lines),
        key=lambda t: (col_fn(t[1]), round(t[1]["y0"]), t[1]["x0"]),
    )
    return [ln for _, ln in keyed], is_multi


def classify_heading(ln, body_size):
    """返回标题级别字符串或 None。"""
    if ln["size"] <= 0:
        return None
    rel = ln["size"] / body_size
    is_head = (rel >= 1.2) or (ln["bold"] and rel >= 1.1)
    if not is_head:
        return None
    text = ln["text"].strip()
    if len(text) > 80:
        return None
    if text.isdigit():  # 纯页码
        return None
    if rel >= 1.6:
        return "#"
    if rel >= 1.35:
        return "##"
    return "###"


def _line_in_rects(ln, rects):
    """判断某文本行中点是否落在任一表格区域内。"""
    if not rects:
        return False
    cx = (ln["x0"] + ln["x1"]) / 2
    cy = (ln["y0"] + ln["y1"]) / 2
    for r in rects:
        try:
            if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
                return True
        except Exception:
            continue
    return False


def build_text_section(lines, page_width, exclude_rects=None):
    """将排序后的文本行拼成 Markdown 文本段落。

    exclude_rects: 表格 bbox 列表，落在其中的文字行将被跳过（避免与表格重复）。
    """
    if not lines:
        return ""
    ordered, _ = order_lines(lines, page_width)
    body_size = body_size_of(lines)
    out = []
    prev = None
    for ln in ordered:
        # 跳过落在表格区域内的文字行（单元格文本已通过表格输出）
        if exclude_rects and _line_in_rects(ln, exclude_rects):
            prev = ln
            continue
        level = classify_heading(ln, body_size)
        if level:
            out.append(f"\n{level} {ln['text']}\n")
            prev = ln
            continue
        if prev is not None:
            gap = ln["y0"] - prev["y1"]
            line_h = max(prev["y1"] - prev["y0"], 1)
            if gap > line_h * PAGE_SEP_GAP_RATIO:
                out.append("")  # 段落间空行
        out.append(ln["text"])
        prev = ln
    text = "\n".join(out).strip()
    # 清理多余空行
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def markdown_table(cells):
    """将二维字符串列表转 Markdown 表格。"""
    if not cells:
        return ""
    cols = max(len(r) for r in cells)
    norm = [r + [""] * (cols - len(r)) for r in cells]

    def esc(v):
        return " " + str(v).replace("|", "\\|").replace("\n", " ") + " "
    header = "|" + "|".join(esc(c) for c in norm[0]) + "|"
    sep = "|" + "|".join("---" for _ in range(cols)) + "|"
    body = "\n".join("|" + "|".join(esc(c) for c in row) + "|" for row in norm[1:])
    return header + "\n" + sep + ("\n" + body if body else "")


def table_has_content(cells):
    if not cells or len(cells) < 1:
        return False
    cols = max((len(r) for r in cells), default=0)
    if cols < 1:
        return False
    non_empty = sum(1 for row in cells for c in row if str(c).strip())
    return non_empty > 0


def extract_tables(page, page_no, tables_dir, preview_dir, dpi, no_tables):
    """提取表格，返回 (md_blocks, json_entries, rects)。

    rects 为各表格的 bbox（fitz.Rect），供正文拼装时剔除落在表格区域内的
    文字行，避免单元格文本与表格重复输出。同时裁切表格区域存 PNG 到
    preview_dir 供人工核对。
    """
    md_blocks = []
    entries = []
    rects = []
    if no_tables:
        return md_blocks, entries, rects
    strategies = ["lines_strict", "text"]
    found = []
    page_w = page.rect.width
    page_h = page.rect.height
    for strat in strategies:
        try:
            finder = page.find_tables(strategy=strat)
        except Exception:
            continue
        if not getattr(finder, "tables", None):
            continue
        for idx, table in enumerate(finder.tables, 1):
            try:
                cells = table.extract()
            except Exception:
                continue
            if not table_has_content(cells):
                continue
            tid = f"p{page_no:03d}_t{idx:02d}"
            md = markdown_table(cells)
            csv_name = f"{tid}.csv"
            csv_path = os.path.join(tables_dir, csv_name)
            try:
                with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f)
                    for row in cells:
                        w.writerow([str(c) for c in row])
            except Exception:
                csv_path = None
            # 表格预览图
            preview_path = None
            try:
                rb = fitz.Rect(table.bbox)
                # 限制裁切在页面范围内
                rb = rb & fitz.Rect(0, 0, page_w, page_h)
                if rb.width > 1 and rb.height > 1:
                    pix = page.get_pixmap(clip=rb, dpi=dpi)
                    pname = f"{tid}.png"
                    pfull = os.path.join(preview_dir, pname)
                    pix.save(pfull)
                    preview_path = "tables_preview/" + pname
            except Exception:
                preview_path = None
            md_blocks.append(md)
            entries.append({
                "id": tid,
                "markdown": md,
                "csv_path": ("tables/" + csv_name) if csv_path else None,
                "preview_path": preview_path,
            })
            try:
                # table.bbox 可能是 tuple 或 fitz.Rect，统一转成 fitz.Rect 以便按 .x0/.y0 取值
                rects.append(fitz.Rect(table.bbox))
            except Exception:
                pass
            found.append(table)
        if found:
            break  # 一个策略成功即止，避免重复
    return md_blocks, entries, rects


def _image_unique_colors(pix, max_samples=2000):
    """估算图片唯一颜色数（下采样），用于低信息量判断。失败返回 None。"""
    try:
        n = pix.n
        w, h = pix.width, pix.height
        samples = pix.samples
        if n not in (3, 4):
            return None
        total = w * h
        if total == 0:
            return None
        step = max(1, total // max_samples)
        colors = set()
        stride = w * n
        for y in range(0, h, step):
            row_off = y * stride
            for x in range(0, w, step):
                off = row_off + x * n
                colors.add((samples[off], samples[off + 1], samples[off + 2]))
                if len(colors) > 256:
                    return len(colors)
        return len(colors)
    except Exception:
        return None


def _page_image_rects(page):
    """返回 {xref: 最大覆盖面积的 fitz.Rect}，用于内容级过滤与 bbox 记录。

    注意：本版本 PyMuPDF 的 page.get_image_info 用 'number'（局部序号）而非
    xref，无法直接映射；改用 page.get_image_rects(xref) 按 xref 取放置区域。
    """
    rects_for = {}
    try:
        for xref, *_ in page.get_images(full=True):
            try:
                rlist = page.get_image_rects(xref)
            except Exception:
                continue
            best = None
            for r in rlist:
                try:
                    rr = fitz.Rect(r)
                except Exception:
                    continue
                if best is None or rect_area(rr) > rect_area(best):
                    best = rr
            if best is not None:
                rects_for[xref] = best
    except Exception:
        rects_for = {}
    return rects_for


def extract_images(doc, page, page_no, images_dir, seen_hashes, no_images):
    """导出页面嵌入图片，按内容去重 + 内容级过滤，返回引用列表（含 bbox）。"""
    refs = []
    if no_images:
        return refs
    rects_for = _page_image_rects(page)
    page_area = page.rect.width * page.rect.height
    page_paths = set()  # 同一页内按内容去重，避免重复引用同一张图
    try:
        img_list = page.get_images(full=True)
    except Exception:
        return refs
    for xref, *_ in img_list:
        try:
            info = doc.extract_image(xref)
        except Exception:
            continue
        data = info.get("image")
        ext = (info.get("ext") or "png").lower()
        if not data:
            continue
        h = sha256_bytes(data)
        if h in seen_hashes:
            rel = seen_hashes[h]
            if rel in page_paths:
                continue  # 同页内同一图多次放置，仅列一次
            r0 = rects_for.get(xref)
            refs.append({"path": rel, "xref": xref,
                         "bbox": [round(r0.x0), round(r0.y0), round(r0.x1), round(r0.y1)] if r0 else None})
            page_paths.add(rel)
            continue
        # 尺寸过滤：用 Pixmap 获取宽高
        try:
            pix = fitz.Pixmap(data)
            w, ht = pix.width, pix.height
        except Exception:
            w, ht = 9999, 9999
        if w < MIN_IMG_SIDE or ht < MIN_IMG_SIDE or (w * ht) < MIN_IMG_AREA:
            continue
        # 内容级过滤
        skip = False
        rb = rects_for.get(xref)
        if rb is not None and page_area > 0:
            cov = rect_area(rb) / page_area
            aspect = max(rb.width, rb.height) / max(min(rb.width, rb.height), 1)
            if cov >= BG_COVERAGE:
                skip = True  # 整页背景图
            elif aspect >= MAX_ASPECT_RATIO:
                skip = True  # 横幅/分隔条
            elif cov >= SOLID_COVERAGE:
                uc = _image_unique_colors(pix)
                if uc is not None and uc <= SOLID_UNIQUE_COLORS:
                    skip = True  # 大面积纯色块
        if skip:
            continue
        fname = f"img_{h[:12]}.{ext}"
        out_path = os.path.join(images_dir, fname)
        try:
            with open(out_path, "wb") as f:
                f.write(data)
        except Exception:
            continue
        rel = "images/" + fname
        seen_hashes[h] = rel
        r0 = rects_for.get(xref)
        refs.append({
            "path": rel, "xref": xref,
            "bbox": [round(r0.x0), round(r0.y0), round(r0.x1), round(r0.y1)] if r0 else None,
        })
        page_paths.add(rel)
    return refs


def is_scanned(lines, page):
    """判定是否需要扫描渲染：文字层几乎为空（<阈值）且页面含图片，视为无文字层的扫描页。"""
    text_chars = sum(len(ln["text"]) for ln in lines)
    try:
        has_img = bool(page.get_images(full=True))
    except Exception:
        has_img = False
    return (text_chars < SCAN_TEXT_THRESHOLD) and has_img, text_chars


# 高置信 mojibake 双字符：UTF-8 被当作 Latin-1 解码的典型产物（西方语言）
MOJI_TOKENS = [
    "Ã©", "Ã¨", "Ã¢", "Ã®", "Ã¯", "Ã´", "Ã»", "Ã¤", "Ã¶", "Ã¼", "Ã±", "Ã§", "Ãª",
    "â€", "â€™", "â€œ", "â€\u009d", "â€“", "â€”",
    "Â°", "Â©", "Â®", "Â´", "Â²", "Â³", "Â¡", "Â¿",
]
# CJK 乱码中常见的 Latin-1 组合/控制符（真实正文中极少单独成串出现）
COMBINING_L1 = set([0xAD, 0xA8, 0xB4, 0xB8,
                    0x02DB, 0x02D8, 0x02D9, 0x02DA, 0x02DC, 0x02DD])


def is_garbled(text):
    """检测乱码/低质文字层（如可变字体导出导致的复制乱码）。

    仅针对高置信信号，避免误伤正常外文/中文文本：
      ① U+FFFD 替换符占比偏高（编码失败）
      ② 出现 Latin-1 mojibake 双字符（UTF-8 被误读为 Latin-1，如 Ã© 代 é）
      ③ CJK 乱码：大量 Latin-1 组合/控制符，且无真实 CJK、无实质 ASCII 词
    命中返回 True。
    """
    if not text:
        return False
    s = "".join(ch for ch in text if not ch.isspace())
    n = len(s)
    if n < 8:
        return False  # 太短无法判断，避免误报
    # ① U+FFFD 替换符
    if s.count("\ufffd") / n > 0.02:
        return True
    # ② mojibake 双字符
    moji = 0
    for tok in MOJI_TOKENS:
        moji += s.count(tok)
    if moji >= 2:
        return True
    if n >= 20 and (moji * 2) / n > 0.05:
        return True
    # ③ CJK 乱码特征
    comb = sum(1 for ch in s if ord(ch) in COMBINING_L1)
    has_cjk = any(0x4E00 <= ord(ch) <= 0x9FFF or 0x3040 <= ord(ch) <= 0x30FF for ch in s)
    ascii_alpha = sum(1 for ch in s if 0x41 <= ord(ch) <= 0x7A)
    if comb >= 3 and not has_cjk and ascii_alpha < n * 0.3:
        return True
    return False


def render_scan(page, page_no, scans_dir, dpi):
    fname = f"p{page_no:03d}.png"
    out_path = os.path.join(scans_dir, fname)
    try:
        pix = page.get_pixmap(dpi=dpi)
        pix.save(out_path)
    except Exception:
        return None
    return "scans/" + fname


# -+
# 超链接 / 大纲
# -+

def extract_links(page):
    """提取页面超链接，返回精简列表 [{kind, uri?, page?}]。"""
    links = []
    try:
        for lk in page.get_links():
            item = {"kind": lk.get("kind")}
            if lk.get("uri"):
                item["uri"] = lk.get("uri")
            pg = lk.get("page")
            if pg is not None:
                item["page"] = pg + 1
            if item.get("uri") or item.get("page") is not None:
                links.append(item)
    except Exception:
        links = []
    return links


# ----------------------------------------------------------------------
# 页面 / 文档级拼装
# ----------------------------------------------------------------------

def extract_page(doc, page, page_no, out_dir, opts):
    page_width = page.rect.width
    page_height = page.rect.height
    lines = collect_lines(page)
    body_size = body_size_of(lines)
    scanned, text_chars = is_scanned(lines, page)
    full_text = "\n".join(ln["text"] for ln in lines)
    garbled = is_garbled(full_text)
    try:
        has_img = bool(page.get_images(full=True))
    except Exception:
        has_img = False

    warnings = []
    page_md_parts = []
    tables_md, tables_json, table_rects = extract_tables(
        page, page_no, os.path.join(out_dir, "tables"),
        os.path.join(out_dir, "tables_preview"), opts["dpi"], opts["no_tables"])
    images_json = extract_images(
        doc, page, page_no, os.path.join(out_dir, "images"),
        opts["seen_hashes"], opts["no_images"])

    text_md = ""
    scan_png = None
    if scanned:
        scan_png = render_scan(page, page_no, os.path.join(out_dir, "scans"), opts["dpi"])
        text_status = "scan_required"
    elif garbled and has_img:
        # 文字层乱码但页面有图（视觉渲染为真实字形）→ 交视觉识别
        scan_png = render_scan(page, page_no, os.path.join(out_dir, "scans"), opts["dpi"])
        text_status = "scan_required"
        warnings.append("garbled_text_detected")
    else:
        text_md = build_text_section(lines, page_width, table_rects)
        text_status = "extracted"
        if garbled:
            warnings.append("garbled_text_detected")

    links = extract_links(page) if not opts["no_links"] else []

    # 拼装页面 Markdown
    page_md_parts.append(f"<!-- page:{page_no} -->")
    page_md_parts.append(f"## 第 {page_no} 页")
    if scan_png:
        page_md_parts.append(
            f"> ⚠️ 该页几乎无文字层或文字层乱码（疑似扫描件/可变字体），已导出 `{scan_png}`，"
            f"待视觉识别后回填此区块。")
    else:
        if text_md:
            page_md_parts.append(text_md)
    for tmd in tables_md:
        page_md_parts.append("")
        page_md_parts.append(tmd)
    for img in images_json:
        page_md_parts.append("")
        page_md_parts.append(f"![图片]({img['path']})")

    page_md = "\n".join(page_md_parts).strip()

    return {
        "page": page_no,
        "text_status": text_status,
        "text_chars": text_chars,
        "tables": tables_json,
        "images": images_json,
        "links": links,
        "scan_png": scan_png,
        "warnings": warnings,
        "md": page_md,
    }


def extract_document(doc, out_dir, opts):
    pages = []
    for i in range(len(doc)):
        page = doc[i]
        try:
            pres = extract_page(doc, page, i + 1, out_dir, opts)
        except Exception as e:
            pres = {
            "page": i + 1, "text_status": "error",
            "text_chars": 0, "tables": [], "images": [], "links": [],
            "scan_png": None,
            "warnings": [f"处理异常: {e}"], "md": "",
            }
        pages.append(pres)
    return pages


def build_markdown(src_path, doc_meta, pages, scan_pages):
    stem = Path(src_path).stem
    lines = [f"# {stem} · 内容提取", ""]
    lines.append("- 源文件: " + src_path)
    lines.append(f"- 页数: {doc_meta.get('page_count', 0)}")
    lines.append(f"- 标题: {doc_meta.get('title', '')}")
    lines.append(f"- 作者: {doc_meta.get('author', '')}")
    if doc_meta.get("outline"):
        lines.append(f"- 大纲(TOC)层级数: {len(doc_meta['outline'])}")
    if scan_pages:
        lines.append("- 扫描页(需视觉识别): " + ", ".join(f"第 {p} 页" for p in scan_pages))
    lines.append("")
    for p in pages:
        if p["md"]:
            lines.append(p["md"])
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--dpi", type=int, default=SCAN_DPI)
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--no-tables", action="store_true")
    ap.add_argument("--no-links", action="store_true")
    args = ap.parse_args()

    # 校验输入
    src = Path(args.input)
    if not src.exists():
        _fail("FILE_NOT_FOUND", f"文件不存在：{args.input}")
    if src.suffix.lower() != ".pdf":
        _fail("NOT_PDF", f"仅支持 PDF，收到：{src.suffix}")

    out_dir = Path(args.output_dir)

    try:
        doc = fitz.open(str(src))
    except Exception as e:
        msg = str(e)
        if "password" in msg.lower():
            _fail("PASSWORD_REQUIRED", "PDF 需要密码")
        _fail("OPEN_FAILED", f"打开 PDF 失败：{msg}")

    # 加密 PDF：fitz.open 不会抛错，需显式检查密码保护
    if getattr(doc, "needs_pass", False) or getattr(doc, "is_encrypted", False):
        try:
            doc.close()
        except Exception:
            pass
        _fail("PASSWORD_REQUIRED", "PDF 需要密码")

    try:
        if len(doc) == 0:
            doc.close()
            _fail("OPEN_FAILED", "PDF 为空，无任何页面")

        meta = doc.metadata or {}
        # 文档大纲
        outline = []
        try:
            toc = doc.get_toc()
            for entry in toc:
                if len(entry) >= 3:
                    outline.append([entry[0], entry[1], entry[2]])
        except Exception:
            outline = []
        doc_meta = {
            "page_count": len(doc),
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "outline": outline,
        }
        # 校验通过后再创建输出目录，避免失败残留空目录
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "images").mkdir(exist_ok=True)
            (out_dir / "tables").mkdir(exist_ok=True)
            (out_dir / "tables_preview").mkdir(exist_ok=True)
            (out_dir / "scans").mkdir(exist_ok=True)
        except Exception as e:
            doc.close()
            _fail("WRITE_FAILED", f"无法创建输出目录：{e}")

        opts = {
            "dpi": args.dpi,
            "no_images": args.no_images,
            "no_tables": args.no_tables,
            "no_links": args.no_links,
            "seen_hashes": {},
        }
        pages = extract_document(doc, out_dir, opts)
        doc.close()
    except SystemExit:
        raise
    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        _fail("UNEXPECTED_ERROR", f"处理异常：{e}")

    scan_pages = [p["page"] for p in pages if p["text_status"] == "scan_required"]
    text_pages = [p["page"] for p in pages if p["text_status"] == "extracted"]
    table_count = sum(len(p["tables"]) for p in pages)
    image_count = sum(len(p["images"]) for p in pages)
    link_count = sum(len(p["links"]) for p in pages)

    md = build_markdown(str(src), doc_meta, pages, scan_pages)
    md_path = out_dir / (src.stem + ".md")
    try:
        md_path.write_text(md, encoding="utf-8")
    except Exception as e:
        _fail("WRITE_FAILED", f"写入 Markdown 失败：{e}")

    result = {
        "ok": True,
        "input": str(src),
        "output_dir": str(out_dir),
        "markdown_path": str(md_path),
        "document_info": doc_meta,
        "pages": [
            {k: v for k, v in p.items() if k != "md"} for p in pages
        ],
        "summary": {
            "text_pages": text_pages,
            "scan_pages": scan_pages,
            "table_count": table_count,
            "image_count": image_count,
            "link_count": link_count,
        },
        "warnings": [],
    }
    _emit(result)


if __name__ == "__main__":
    main()
