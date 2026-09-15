# Changelog

---

## 2.2.4 · 2026-09-14

v2.2.4：表格输出规整 —— 新增「**合并单元格语义归位**」与「**空列剔除**」，让重跑直接产出可用的干净表格
（此前 PO 4469 需人工二次整理）（缓存因脚本版本号变化自动失效一次）：

- **合并单元格语义归位**（新增 `relocate_merged_cells` + `_grid_columns` + `_column_of`）：
  跨列合并单元格（典型是合计行的 `Total  $1,489.00`）在 `table.extract()` 里会被整串塞进**最左边那个栅格列**
  （常常是隐藏列），导致 CSV 凭空多一列、金额错位。现在改用 `page.get_text("words", clip=cell_bbox)` 取词，
  按**词心 x** 落入的栅格列重新分配。选 words 而非 `get_textbox`：不会把跨界的词截断，也不会重复。
  栅格列边界用表头行的 `header.cells`，表头为 `None` 的列用相邻边界插值成零宽占位以保证**列索引与 extract() 一一对应**；
  表头不可用时退化为 cells 最多的一行。实测 PO 4469：`Total`（词心 436.1）→ Description 列、`$1,489.00`（词心 540.2）→ Amount 列，
  与人工整理结果逐格一致；普通明细行单元格不跨列，完全不受影响。
- **重排的三道安全阀**（`_has_column_gap` / `MERGE_MAX_GROUPS` / 目标列须为空）—— 重排会把文字在列间搬家，误判代价远大于漏判，故从严：
  1. **落点列数 ≤ 2**：一句横跨整行的说明文字会落到 ≥3 列，直接放弃；
  2. **同行的跨列相邻词，空隙必须 ≥ 1.5 × 字高**：实测真·双字段（`Total`→`$1,489.00`）gap/字高 = **6.32**，
     而被栅格切开的正常词组（条码标签 `Item No. 50890`）只有 **0.20**，阈值 1.5 两侧各有 4~7 倍余量；
  3. **跨列分属不同列、却不在同一行的，一律放弃**：实测报关放行单格内第一行 `境内货源地(33199)`、第二行 `东阳`
     被切到两列，值跑到标签左边 —— 属于列边界切在正常多行文字中间，须拦住。
  最终回归（**700 份 PDF / 890 张表**，取自 `E:\CXD 资料\04_客户` 下 ≤3MB 体积最大的 700 份，每份扫前 3 页）：
  **词元多重集零丢失、行数零变化**；重排 5 处且**全部是期望行为**（报关资料 `TOTAL: $21,885.12` / `$26,874.00` / `2872.0000` / `$61,204.84`
  归位到「货名与数量 + 总值」两列）；正例 PO 4469 仍正常重排，反例（条码标签 `Item No. 50890`、报关放行单）均被正确拦住。
  注意：样本按体积从大到小取，是**有意偏向复杂版式的抽样、非随机**；>3MB 的 552 份与每份第 4 页之后不在覆盖范围。
- 元数据：`displayName` 改为 `PDF Structured Extractor`（仅用于显示）。`name` 必须保持 `pdf-structured-extractor` ——
  官方 `skill-creator/scripts/quick_validate.py` 要求 `^[a-z0-9-]+$`，**空格与大写均不合规**。
- **空列剔除**（新增 `drop_empty_columns`）：删除**所有行都为空**的列（隐藏列 / 边框伪列）。
  判定标准是全表皆空，故不可能误删数据。实测 PO 4469：由 8 列收敛为 6 列（Item/MPN/Description/Qty/Rate/Amount），
  消失的两列分别是 `header.cells` 为 `None` 的隐藏列与宽 4.93pt 的右边框伪列。
- 开关：`NORMALIZE_TABLE = True`（置 False 可还原 PyMuPDF 原始 `extract()` 结果做对比）。

## 2.2.3 · 2026-09-14

v2.2.3：修复「行间无横线的表格被并成一行」（缓存因脚本版本号变化自动失效一次）：

- **策略顺序**：`extract_tables` 的 `strategies` 由 `["lines_strict", "text"]` 改为 `["lines", "lines_strict", "text"]`。
  PyMuPDF 1.28.2 `pymupdf/table.py` 的真实语义：`lines` = `filter_edges(EDGES,"h"/"v")` 取**矢量线 + 填充矩形（底纹）的边界**；
  `lines_strict` = `filter_edges(..., edge_type="line")` **只认矢量线段、丢弃所有填充矩形**；`text` = `words_to_edges_h/v` 纯按文字位置推边。
  原顺序下 `lines_strict` 首先生效即 `break`，`lines` **从未被调用过**；而订单/报价单类表格常常行间没有横线、
  只靠**隔行底纹（zebra shading）**分行 → `lines_strict` 把底纹一并丢掉 → 明细区一条内部水平边都不剩 →
  N 个明细行被并成 1 行、单元格内用 `\n` 拼接。实测 PO 4469：3 行 vs 正确的 7 行（`lines` 的行边界
  362.65/419.65/476.65/522.25 与填充矩形边界 362.6/419.6/476.6/522.2 一一对应，误差 0.05pt）。
  注意 `lines` 会把表格区内**任何**填充矩形当边界，表内有装饰色块时可能过度切分，故保留 `lines_strict`/`text` 作兜底。

- **None 处理**：`markdown_table` 的 `esc()`、CSV 写入循环、`table_has_content` 三处把 `None` 当普通值 `str()`，
  导致空单元格输出字面量 `"None"`，且全空行会被误判为「有内容」。统一改为 `None` → 空串。

- 说明：另测 `refine=True`，行数同样能切对（7 行），但会把 `extract()` 的 row0 变成「表头 + 首行数据」的合并行
  （`Item\nCNDL-GRACE002M-IV-HG`）并导致首行重复出现一次，需额外清理才能用，故未采用。

## 2.2.2 · 2026-09-04

v2.2.2：代码审查后的缺陷修复与冗余清理（无功能/输出变化，回归基线逐字节一致）：
- **修复颜色采样 bug**（`_image_unique_colors`）：原一维步长用在二维循环，800×500 图仅采 12 点（目标 2000），会误杀高频内容的图（条纹/密集线条）判成纯色块。改为 x/y 各按 `sqrt` 拆分步长，实测 2088 点、正确识别。
- **删除死代码**：未使用的 `import io`；`extract_page` 内算完未用的 `body_size`；从未被读的 `opts["no_cache"]`；恒为空的顶层 `result["warnings"]`；`extract_tables` 中仅用于 break 判断的 `found` 列表。
- **性能**：每页 `page.get_images()` 调用从 4 次降到 2 次（新增 `has_images()`，并让 `_page_image_rects` 复用调用方的 img_list）。
- **去重重构**：`build_text_section` 与 `build_text_section_plain` 合并为带 `plain` 参数的单函数。
- **小修**：`while "\n\n\n"` 冗余替换改 `re.sub(r"\n{3,}", "\n\n", …)`；`set([…])` → `{…}`；`table_has_content` 冗余条件；mojibake 注释的 "Latin-1" 改为更准确的 cp1252。
- **文档**：SKILL.md / README 的 JSON 契约表补 `summary.text_pages`；版本号同步至 2.2.2（缓存因此失效一次）。

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

