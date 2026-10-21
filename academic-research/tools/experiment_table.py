# -*- coding: utf-8 -*-
"""experiment_table.py — 微调实验对比表/消融表一键生成（academic-research 技能 v3.0）

把实验结果 CSV 一键转成论文级 Word 三线表：

  对比表模式：method + 指标列（支持 <指标>_mean/_std 自动合并 mean±std），
             每列最优值自动加粗（方向按指标名推断或 --metrics 显式指定），
             --baseline 指定基线行后自动加 Δ 提升量列。
  消融表模式：--factor-cols 指定因子列原样呈现；--components 指定 0/1 开关列，
             自动渲染为 ✓/✗；指标列同样最优值加粗。

设计原则（与技能其余工具一致）：
  1. 默认即满意初版：零参数跑通规范对比表（指标方向按名字推断、最优加粗、
     mean±std 合并、居中三线表）；
  2. 灵活度只做微调：指标方向/基线/Δ列/表题表注均可一行参数覆盖；
  3. 输出同时给 docx 与 markdown 预览，所见即所得。

用法：
  python experiment_table.py 结果.csv                          # 自动识别结构
  python experiment_table.py 结果.csv --baseline "Full-FT" --delta
  python experiment_table.py 消融.csv --components "data_clean,cosine_lr,early_stop"
  python experiment_table.py --demo                            # 两个样例全量自验

> AI生成
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from three_line_table import df_to_three_line_table  # noqa: E402

DEFAULT_OUT = Path(".temp") / "experiment_table"

# 越小越好的指标关键词（其余默认越大越好）
_LOWER_BETTER = ("loss", "err", "wer", "ppl", "perplexity", "latency",
                 "time", "cost", "params", "flops", "memory", "显存", "耗时")

_TRUE_TOKENS = {"1", "true", "yes", "y", "+", "✓", "✔", "on", "有"}
_FALSE_TOKENS = {"0", "false", "no", "n", "-", "✗", "✘", "off", "无", ""}


def _infer_direction(col):
    """指标列 → 'max'/'min'：先精确后缀（_mean），再整名关键词。"""
    lc = col.lower().replace("_mean", "").replace("_std", "")
    return "min" if any(k in lc for k in _LOWER_BETTER) else "max"


def _parse_metrics_arg(s):
    """--metrics "acc:max,f1:min" → {"acc":"max","f1":"min"}。"""
    out = {}
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            k, v = part.rsplit(":", 1)
            out[k.strip()] = v.strip()
        else:
            out[part] = None  # 占位，后续推断
    return out


def _find_metric_cols(df, method_col, factor_cols, component_cols):
    """指标列 = 数值列，排除 method/因子/组件列；<m>_mean 折成指标名 m。"""
    skip = {method_col} | set(factor_cols) | set(component_cols)
    metrics = {}
    for c in df.columns:
        if c in skip:
            continue
        base = c
        if c.lower().endswith("_mean"):
            base = c[:-5]
        elif c.lower().endswith("_std"):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            metrics[base] = c
    return metrics


def _detect_components(df, candidates):
    """0/1/✓/✗/+/- 语义的列自动识别为开关组件列。"""
    out = []
    for c in candidates:
        vals = {str(v).strip().lower() for v in df[c].dropna().unique()}
        if vals and vals <= (_TRUE_TOKENS | _FALSE_TOKENS):
            out.append(c)
    return out


def _render_switch(v):
    return "✓" if str(v).strip().lower() in _TRUE_TOKENS else "✗"


def build_table(df, *, method_col=None, metrics=None, baseline=None,
                delta=False, factor_cols=None, component_cols=None,
                decimals=2):
    """核心：结果 DataFrame → 展示 DataFrame + bold 判定 + 元信息。

    返回 (display_df, bold_mask(与display_df同形), info dict)
    """
    df = df.copy()
    factor_cols = factor_cols or []
    component_cols = component_cols or []
    if method_col is None:
        # 首个非数值/低基数列当方法列
        method_col = df.columns[0]

    metrics_map = _find_metric_cols(df, method_col, factor_cols, component_cols)
    if metrics:  # 用户显式指定子集/方向
        metrics_map = {k: metrics_map[k] for k in metrics if k in metrics_map}
    directions = {}
    for m, col in metrics_map.items():
        explicit = (metrics or {}).get(m)
        directions[m] = explicit or _infer_direction(m if m != col else col)

    # ---- 最优值加粗掩码（在合并 ± 前按 mean 列判定）----
    best_idx = {}
    for m, col in metrics_map.items():
        base_col = col if col.lower().endswith("_mean") else col
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().sum() == 0:
            continue
        best_idx[m] = int(series.idxmax() if directions[m] == "max" else series.idxmin())

    # ---- Δ 提升量列（相对 baseline 行）----
    delta_cols = {}
    if delta and baseline is not None:
        bmask = df[method_col].astype(str) == str(baseline)
        if not bmask.any():
            raise SystemExit(f"[baseline 未命中] 在 {method_col} 列中找不到 '{baseline}'")
        brow = df[bmask].iloc[0]
        for m, col in metrics_map.items():
            dname = f"Δ{m}"
            base_v = float(brow[col]) if pd.notna(brow[col]) else float("nan")
            vals = pd.to_numeric(df[col], errors="coerce") - base_v
            delta_cols[dname] = [("—" if bmask.iloc[i] or pd.isna(vals.iloc[i])
                                  else f"{vals.iloc[i]:+.{decimals}f}")
                                 for i in range(len(df))]

    # ---- 展示层组装：因子列(原样) + 组件列(✓/✗) + 指标列(mean±std合并) ----
    disp = pd.DataFrame()
    disp[method_col] = df[method_col]
    for c in factor_cols:
        disp[c] = df[c]
    for c in component_cols:
        disp[c] = df[c].map(_render_switch)
    bold_src_cols = {}  # 展示列名 -> (metric_key, is_boldable)
    for m, col in metrics_map.items():
        std_col = col[:-5] + "_std" if col.lower().endswith("_mean") else (
            col + "_std")
        if col.lower().endswith("_mean") and std_col in df.columns:
            disp[m] = [f"{m_:.2f}±{s_:.2f}" if pd.notna(m_) and pd.notna(s_) else "—"
                       for m_, s_ in zip(pd.to_numeric(df[col], errors="coerce"),
                                         pd.to_numeric(df[std_col], errors="coerce"))]
        else:
            disp[m] = pd.to_numeric(df[col], errors="coerce").map(
                lambda v: "—" if pd.isna(v) else f"{v:.{decimals}f}")
        bold_src_cols[m] = m
    for dname, vals in delta_cols.items():
        disp[dname] = vals

    # bold_mask：与 disp 同形的布尔表
    bold_mask = pd.DataFrame(False, index=disp.index, columns=disp.columns)
    for m, i_best in best_idx.items():
        if m in bold_src_cols:
            bold_mask.loc[i_best, m] = True
    info = {"method_col": method_col, "metrics": list(metrics_map),
            "directions": directions, "best_idx": best_idx,
            "n_metrics": len(metrics_map)}
    return disp, bold_mask, info


def to_markdown(disp, bold_mask, info):
    """Markdown 预览（最优值 **加粗**）。"""
    lines = ["| " + " | ".join(disp.columns) + " |",
             "|" + "---|" * len(disp.columns)]
    for i in range(len(disp)):
        cells = []
        for c in disp.columns:
            v = str(disp.iloc[i][c])
            cells.append(f"**{v}**" if bold_mask.iloc[i][c] else v)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run(csv_path, *, method_col=None, metrics=None, baseline=None, delta=False,
        factor_cols=None, component_cols=None, auto_components=True,
        caption=None, note=None, decimals=2, out=None):
    """端到端：CSV → 解析 → docx 三线表 + markdown 预览。"""
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    factor_cols = factor_cols or []
    if component_cols is None:
        candidates = [c for c in df.columns
                      if c != method_col and c not in factor_cols
                      and not pd.api.types.is_numeric_dtype(df[c])]
        # 数值型 0/1 也可能是开关，一并试
        candidates += [c for c in df.columns
                       if c != method_col and c not in factor_cols
                       and pd.api.types.is_numeric_dtype(df[c])
                       and df[c].dropna().isin([0, 1]).all()]
        component_cols = _detect_components(df, candidates) if auto_components else []
    metrics_map = _parse_metrics_arg(metrics)
    disp, mask, info = build_table(
        df, method_col=method_col, metrics=metrics_map or None,
        baseline=baseline, delta=delta, factor_cols=factor_cols,
        component_cols=component_cols, decimals=decimals)

    md = to_markdown(disp, mask, info)
    print(md)

    out_dir = Path(out).parent if out else DEFAULT_OUT
    docx_path = Path(out) if out else out_dir / (csv_path.stem + "_三线表.docx")
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    caption = caption or f"表1 实验结果对比（{csv_path.stem}）"
    note = note or "注：最优值加粗；mean±std 为多次独立实验统计；演示数据为人工构造。"
    df_to_three_line_table(disp, caption=caption, note=note,
                           save_path=docx_path,
                           bold_if=lambda c, v, i: bool(mask.loc[i, c]))
    md_path = docx_path.with_suffix(".md")
    md_path.write_text(md + "\n\n> AI生成\n", encoding="utf-8")
    return {"docx": docx_path, "markdown": md_path, "info": info}


def _demo():
    samples = TOOLS_DIR.parent / "samples"
    print("■ 对比表（微调策略对比，baseline + Δ列）")
    run(samples / "demo_finetune_results.csv",
        baseline="Full-FT", delta=True,
        caption="表1 告警工单分类任务各微调策略性能对比（演示数据）")
    print("\n■ 消融表（组件开关 ✓/✗）")
    run(samples / "demo_ablation.csv",
        component_cols=["data_clean", "cosine_lr", "early_stop"],
        caption="表2 LoRA 微调消融实验（演示数据）")


def main(argv=None):
    try:  # Windows GBK 控制台无法编码 ✓/⚠ 等符号：替换而非崩溃（v2.1.1）
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="微调实验对比表/消融表 → Word 三线表（最优加粗/Δ提升/✓✗开关）")
    ap.add_argument("csv", nargs="?", help="实验结果 CSV")
    ap.add_argument("--method-col", default=None, help="方法名列（默认首列）")
    ap.add_argument("--metrics", default=None,
                    help='指标方向 "acc:max,loss:min"（缺省按列名推断）')
    ap.add_argument("--baseline", default=None, help="基线方法名（配合 --delta 出 Δ列）")
    ap.add_argument("--delta", action="store_true", help="加 Δ 相对基线提升量列")
    ap.add_argument("--factor-cols", default=None, help="消融因子列（原样呈现），逗号分隔")
    ap.add_argument("--components", default=None, help="组件开关列（✓/✗渲染），逗号分隔")
    ap.add_argument("--caption", default=None, help="表题")
    ap.add_argument("--note", default=None, help="表注")
    ap.add_argument("--decimals", type=int, default=2, help="小数位（默认2）")
    ap.add_argument("--out", default=None, help="输出 docx 路径")
    ap.add_argument("--demo", action="store_true", help="两个样例全量自验")
    args = ap.parse_args(argv)
    if args.demo:
        _demo()
        return
    if not args.csv:
        ap.print_help()
        return
    run(args.csv, method_col=args.method_col, metrics=args.metrics,
        baseline=args.baseline, delta=args.delta,
        factor_cols=[c.strip() for c in (args.factor_cols or "").split(",") if c.strip()],
        component_cols=[c.strip() for c in args.components.split(",") if c.strip()] if args.components else None,
        caption=args.caption, note=args.note, decimals=args.decimals,
        out=args.out)


if __name__ == "__main__":
    main()
