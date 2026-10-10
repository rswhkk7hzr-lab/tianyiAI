# -*- coding: utf-8 -*-
"""
three_line_table.py — 学术三线表生成脚本（academic-research 技能 v1.2）

把 pandas DataFrame 一键转为符合学术规范的 Word 三线表：
  顶线/底线 1.5pt、栏目线 0.75pt、无竖线；
  数字列右对齐、文字列左对齐、表头居中；
  支持"均值±标准差"合并列、显著性星号、表注、编号标题。

依赖：python-docx（缺失时提示安装命令，不静默失败）。
用法示例：
    from three_line_table import df_to_three_line_table
    df_to_three_line_table(df, caption="表1 各模型在不同数据集上的测试准确率",
                           note="注：* p<0.05，** p<0.01；数据为5次独立重复实验的均值±标准差。",
                           save_path="表1.docx")
"""

from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    raise SystemExit("[依赖缺失] 请先安装 pandas：pip install pandas")

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
except ImportError:  # pragma: no cover
    raise SystemExit("[依赖缺失] 请先安装 python-docx：pip install python-docx")

DEFAULT_OUT = Path(".temp") / "tables"

# 中文字体（与技能 mplstyle 的中文兜底策略一致）
_ZH_FONTS = ["SimSun", "SimHei", "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei"]


# ---------------------------------------------------------------------------
# 底层 XML 工具
# ---------------------------------------------------------------------------

def _set_cell_border(cell, top=None, bottom=None):
    """按线宽(pt*8=八分之一点)设置单元格上下边框；None 表示该边无线。"""
    tcPr = cell._tc.get_or_add_tcPr()
    # 移除已有边框定义，避免叠加
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for edge, sz in (("top", top), ("bottom", bottom)):
        el = OxmlElement(f"w:{edge}")
        if sz is None:
            el.set(qn("w:val"), "nil")  # 显式无线
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))       # 单位：1/8 pt
            el.set(qn("w:color"), "000000")
        borders.append(el)
    # 左右显式无线（三线表无竖线）
    for edge in ("left", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tcPr.append(borders)


def _set_run_font(run, size_pt=10.5, bold=False):
    """统一字体：中文宋体、西文 Times New Roman（学术论文惯例）。"""
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.name = "Times New Roman"
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    rFonts.set(qn("w:eastAsia"), _ZH_FONTS[0])


def _fill_cell(cell, text, *, align="center", bold=False, size_pt=10.5):
    """写入单元格文本并设置对齐/字体。align: left/center/right。"""
    cell.text = ""
    para = cell.paragraphs[0]
    para.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT,
                      "center": WD_ALIGN_PARAGRAPH.CENTER,
                      "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    # 收紧段落间距，表格更紧凑
    pf = para.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    run = para.add_run(str(text))
    _set_run_font(run, size_pt=size_pt, bold=bold)


# ---------------------------------------------------------------------------
# 对外主函数
# ---------------------------------------------------------------------------

def df_to_three_line_table(df, caption=None, note=None, save_path=None,
                           align=None, index=False, index_label="",
                           mean_sd_cols=None, decimals=2, sig_map=None):
    """DataFrame → Word 三线表（.docx）。

    对齐规范：**默认全表居中**（高校学位论文模板主流）；投期刊需数字列右对齐时，
    用 align 参数指定，如 align={"准确率": "right", "n": "right"}。
    长表跨页时表头自动重复（tblHeader）。

    参数
    ----
    df : pandas.DataFrame
    caption : 表标题，如 "表1 各模型的测试准确率对比"（置于表上方，居中）
    note : 表注，如 "注：* p<0.05"（置于表下方，字号小于正文，左对齐）
    align : 各列对齐字典 {"列名": "left"/"center"/"right"}；缺省全部居中
    index : 是否把 DataFrame 索引作为首列（如聚合表的分组键）
    index_label : 索引列的表头文字
    mean_sd_cols : 需要合并为 "均值±标准差" 的列对列表，如 [("mean", "std")]（保序）
    decimals : 数值列保留小数位
    sig_map : 数值→星号映射函数，如 lambda v: "***" if v > 0.99 else ""

    返回
    ----
    dict：{"save_path": Path}
    """
    # ---- 数据准备：均值±SD 合并列（保序：合并列插回原 mean 列位置）----
    if mean_sd_cols:
        for mean_col, sd_col in mean_sd_cols:
            if mean_col in df.columns and sd_col in df.columns:
                pos = df.columns.get_loc(mean_col)
                combined = df.apply(
                    lambda r: f"{r[mean_col]:.{decimals}f}±{r[sd_col]:.{decimals}f}",
                    axis=1)
                df = df.drop(columns=[mean_col, sd_col])
                df.insert(pos, mean_col, combined)

    if index:
        df = df.reset_index()
        if index_label and "index" in df.columns:
            df = df.rename(columns={"index": index_label})

    n_rows, n_cols = df.shape
    doc = Document()
    # 页边距按学位论文惯例（上下2.54cm，左右3.17cm）——与多数高校规范一致
    for section in doc.sections:
        section.top_margin = Pt(72)
        section.bottom_margin = Pt(72)
        section.left_margin = Pt(90)
        section.right_margin = Pt(90)

    # ---- 表标题（表注置表上、图注置图下的学术惯例）----
    if caption:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(caption)
        _set_run_font(run, size_pt=10.5, bold=True)

    # ---- 建表 ----
    table = doc.add_table(rows=n_rows + 1, cols=n_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    # 表头（恒居中加粗）
    for j, col in enumerate(df.columns):
        _fill_cell(table.rows[0].cells[j], col, align="center", bold=True)
    # 表头跨页自动重复（学位论文长表痛点：跨页后表头不丢失）
    trPr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    trPr.append(tbl_header)
    # 数据行：默认居中（高校学位论文规范）；align 可覆盖为期刊式对齐
    for i in range(n_rows):
        for j, col in enumerate(df.columns):
            val = df.iat[i, j]
            col_align = (align or {}).get(col)
            if col_align is None:  # 默认学位论文规范：全表居中
                col_align = "center"
            text = val
            if isinstance(val, float):
                text = f"{val:.{decimals}f}"
                if sig_map:
                    text += sig_map(val)
            _fill_cell(table.rows[i + 1].cells[j], text, align=col_align)

    # ---- 三线（顶线1.5pt=12、栏目线0.75pt=6、底线1.5pt=12）----
    for j in range(n_cols):
        _set_cell_border(table.rows[0].cells[j], top=12, bottom=6)
        _set_cell_border(table.rows[-1].cells[j], top=None, bottom=12)
        for i in range(1, n_rows):
            _set_cell_border(table.rows[i].cells[j], top=None, bottom=None)

    # ---- 表注 ----
    if note:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(note)
        _set_run_font(run, size_pt=9)  # 表注字号小于正文

    # ---- 保存 ----
    if save_path is None:
        out = DEFAULT_OUT / "three_line_table.docx"
    else:
        out = Path(save_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return {"save_path": out}


# ---------------------------------------------------------------------------
# 演示入口：python three_line_table.py --demo
# ---------------------------------------------------------------------------

def _demo():
    samples = Path(__file__).resolve().parent.parent / "samples"
    df = pd.read_csv(samples / "demo_group_comparison.csv")
    agg = (df.groupby(["dataset", "model"])["accuracy"]
             .agg(["mean", "std", "count"]).reset_index())
    agg = agg.rename(columns={"dataset": "数据集", "model": "模型",
                              "mean": "准确率", "count": "n"})
    result = df_to_three_line_table(
        agg[["数据集", "模型", "准确率", "n"]],
        caption="表1 各模型在不同数据集上的测试准确率（演示数据）",
        note="注：数据为5次独立重复实验的统计结果；演示数据为人工构造，仅用于功能展示。",
        mean_sd_cols=None,
        save_path=DEFAULT_OUT / "demo_table1.docx")
    print("三线表示例 →", result["save_path"])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="学术三线表生成脚本")
    ap.add_argument("--demo", action="store_true", help="用 samples/ 数据生成三线表示例")
    args = ap.parse_args()
    if args.demo:
        _demo()
    else:
        ap.print_help()
