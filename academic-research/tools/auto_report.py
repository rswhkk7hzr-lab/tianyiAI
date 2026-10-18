# -*- coding: utf-8 -*-
"""
auto_report.py — CSV 一键分析报告（academic-research 技能 v1.2 · 核心创新模块）

流程：CSV → 数据质量检查 → 智能图表推荐 → 自动出图 → 自动统计检验 → 结果章节文字
     → 汇总输出 Markdown 分析报告（含全部图表路径与规范统计报告格式）

设计原则：
  1. 智能推荐是"建议"不是"决定"：推荐结果打印给用户/上层智能体确认，
     非 --yes 模式下只出推荐与预览，不擅自选型（人机协同）
  2. 统计检验严格按指南第 2 节决策表执行：先验前提（正态性/方差齐性），
     再选方法；非正态自动走非参数路径，不强行 t 检验
  3. 数据诚实：样本量、检验统计量、p 值均由真实计算得出；报告脚注
     标注数据质量检查结果，缺失/离群如实呈现
  4. 报告文字仅覆盖"结果描述"层：客观描述统计量与差异方向，
     不代用户解释"为什么"（科学解释权归作者）

用法：
  python auto_report.py data.csv                       # 交互推荐模式（打印推荐）
  python auto_report.py data.csv --yes                 # 全自动：按推荐直接执行
  python auto_report.py data.csv --group model --value acc --yes
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy import stats as sps
except ImportError:
    sps = None

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import plot_templates as pt  # noqa: E402  复用样式/模板/配方存档能力

DEFAULT_OUT = Path(".temp") / "autoreport"


# ---------------------------------------------------------------------------
# Step 1 数据质量检查（对应指南第 1 节清单）
# ---------------------------------------------------------------------------

def check_data_quality(df):
    """按指南第 1 节执行质量检查，返回结构化结果 dict。"""
    report = {"n_rows": int(len(df)), "n_cols": int(df.shape[1]),
              "columns": {}, "issues": []}
    for col in df.columns:
        s = df[col]
        info = {"dtype": str(s.dtype)}
        if pd.api.types.is_numeric_dtype(s):
            desc = s.describe()
            info.update({"missing_pct": round(float(s.isna().mean()) * 100, 2),
                         "mean": round(float(desc["mean"]), 4),
                         "std": round(float(desc["std"]), 4),
                         "min": round(float(desc["min"]), 4),
                         "max": round(float(desc["max"]), 4)})
            # 1.5×IQR 离群值标记（只标记不删除）
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            n_out = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
            info["iqr_outliers_marked"] = n_out
        else:
            info.update({"missing_pct": round(float(s.isna().mean()) * 100, 2),
                         "n_unique": int(s.nunique())})
        report["columns"][col] = info
        if info.get("missing_pct", 0) > 20:
            report["issues"].append(f"列 {col} 缺失比例 {info['missing_pct']}%（>20%，慎用）")
        if info.get("iqr_outliers_marked", 0) > 0:
            report["issues"].append(
                f"列 {col} 按 1.5×IQR 标记到 {info['iqr_outliers_marked']} 个离群值（已标记，未删除）")
    if report["n_rows"] < 8:
        report["issues"].append(f"样本量仅 {report['n_rows']} 行，统计检验效力有限，结果仅供参考")
    return report


# ---------------------------------------------------------------------------
# Step 2 智能图表推荐（列结构 → 图表类型建议）
# ---------------------------------------------------------------------------

def recommend_charts(df):
    """基于列结构推荐图表类型与理由（可执行化的"图表类型选择"表）。"""
    cat_cols = [c for c in df.columns
                if not pd.api.types.is_numeric_dtype(df[c])]
    num_cols = [c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 5]
    recs = []
    if cat_cols and num_cols:
        for y in num_cols[:2]:
            for x in cat_cols[:2]:
                recs.append({
                    "template": "grouped_bar", "x": x, "y": y,
                    "reason": f"「{x}」为类别（{df[x].nunique()} 类）、「{y}」为数值 → 组间均值比较首选分组柱状图（自动附误差线）",
                    "also": "grouped_box（若需展示分布/离群值）"})
                recs.append({
                    "template": "grouped_box", "x": x, "y": y,
                    "reason": f"展示「{y}」在「{x}」各组的分布、中位数与离群值（数据非正态时更稳健）",
                    "also": "grouped_bar"})
    if len(num_cols) >= 2:
        x, y = num_cols[0], num_cols[1]
        recs.append({
            "template": "scatter_fit", "x": x, "y": y,
            "reason": f"「{x}」与「{y}」均为连续数值 → 散点+拟合线（自动报告 Pearson/Spearman）",
            "also": "plot_line（若 x 为时间/轮次序）"})
        if df[x].is_monotonic_increasing or x.lower() in ("epoch", "step", "time", "iter", "round"):
            recs[-1]["template"] = "plot_line"
            recs[-1]["reason"] = f"「{x}」呈单调递增/为序数列 → 趋势演变首选折线图（自动标注最优值）"
    if len(num_cols) >= 3:
        recs.append({
            "template": "heatmap", "x": None, "y": None,
            "reason": f"存在 {len(num_cols)} 个数值列 → 相关矩阵热力图（先 df.corr()）",
            "also": None})
    return recs[:6]


# ---------------------------------------------------------------------------
# Step 3 自动统计检验（严格按指南第 2 节决策表）
# ---------------------------------------------------------------------------

def _fmt_p(p):
    if p is None:
        return "NA"
    return "<0.001" if p < 0.001 else f"={p:.3f}"


def auto_group_test(df, x, y):
    """组间比较：先验前提（正态性逐组 Shapiro + 方差齐性 Levene），再按决策表选方法。

    返回 dict：方法名、统计量字符串、p 值、效应量、前提检验详情。
    """
    groups = [g[x and y].dropna().values for _, g in df.groupby(x, observed=True)]
    k = len(groups)
    n_total = int(sum(len(g) for g in groups))
    result = {"comparison": f"{y} ~ {x}", "k_groups": k, "n_total": n_total,
              "premise": {}, "method": None, "stat": None, "p": None, "effect": None}

    if k < 2:
        result["method"] = "跳过（组数<2）"
        return result

    # 前提：逐组正态性（Shapiro-Wilk，n<50 适用）
    shapiro = []
    for _, g in df.groupby(x, observed=True):
        vals = g[y].dropna().values
        if len(vals) >= 3 and sps is not None:
            st, p = sps.shapiro(vals)
            shapiro.append({"group": str(_.iloc[0] if hasattr(_, "iloc") else _),
                            "W": round(float(st), 3), "p": round(float(p), 4),
                            "normal": bool(p > 0.05)})
    result["premise"]["shapiro"] = shapiro
    all_normal = bool(shapiro) and all(s["normal"] for s in shapiro)

    # 前提：方差齐性（Levene）
    if sps is not None and all(len(g) >= 2 for g in groups):
        st, p = sps.levene(*groups)
        result["premise"]["levene"] = {"W": round(float(st), 3),
                                       "p": round(float(p), 4),
                                       "equal_var": bool(p > 0.05)}
        equal_var = p > 0.05
    else:
        equal_var = None

    # 按决策表选方法
    if k == 2:
        if all_normal and equal_var is not False:
            st, p = sps.ttest_ind(groups[0], groups[1])
            # Cohen's d
            import numpy as _np
            n1, n2 = len(groups[0]), len(groups[1])
            sp = _np.sqrt(((n1 - 1) * _np.var(groups[0], ddof=1)
                           + (n2 - 1) * _np.var(groups[1], ddof=1)) / (n1 + n2 - 2))
            d = float((groups[0].mean() - groups[1].mean()) / sp) if sp > 0 else None
            result.update({"method": "独立样本 t 检验",
                           "stat": f"t({n1 + n2 - 2})={st:.2f}",
                           "p": float(p), "effect": f"Cohen's d={d:.2f}" if d is not None else None})
        elif all_normal:
            st, p = sps.ttest_ind(groups[0], groups[1], equal_var=False)
            result.update({"method": "Welch t 检验（方差不齐）",
                           "stat": f"Welch t={st:.2f}", "p": float(p), "effect": None})
        else:
            st, p = sps.mannwhitneyu(groups[0], groups[1])
            result.update({"method": "Mann-Whitney U（非正态）",
                           "stat": f"U={st:.1f}", "p": float(p), "effect": None})
    else:  # k >= 3
        if all_normal and equal_var is not False:
            st, p = sps.f_oneway(*groups)
            # η² 效应量
            grand = df[y].dropna().mean()
            ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
            ss_total = ((df[y].dropna() - grand) ** 2).sum()
            eta2 = float(ss_between / ss_total) if ss_total > 0 else None
            result.update({"method": "单因素 ANOVA",
                           "stat": f"F({k - 1},{n_total - k})={st:.2f}",
                           "p": float(p),
                           "effect": f"η²={eta2:.3f}" if eta2 is not None else None,
                           "posthoc": "Tukey HSD（需 statsmodels，或人工两两比较 + Bonferroni 校正）"})
        elif all_normal:
            st, p = sps.f_oneway(*groups)  # scipy 无 Welch ANOVA，注明
            result.update({"method": "ANOVA（建议 Welch ANOVA，方差不齐）",
                           "stat": f"F({k - 1},{n_total - k})={st:.2f}", "p": float(p),
                           "effect": None})
        else:
            st, p = sps.kruskal(*groups)
            result.update({"method": "Kruskal-Wallis（非正态）",
                           "stat": f"H={st:.2f}", "p": float(p),
                           "posthoc": "Dunn 事后检验 + 多重比较校正", "effect": None})
    return result


def auto_correlation(df, x, y):
    """两连续变量关联：Pearson + Spearman 双报告（前提不满足时以 Spearman 为准）。"""
    d = df[[x, y]].dropna()
    if len(d) < 3 or sps is None:
        return None
    pr = sps.pearsonr(d[x], d[y])
    sr = sps.spearmanr(d[x], d[y])
    # 正态性（Shapiro，n<50）
    normal = all(sps.shapiro(d[c])[1] > 0.05 for c in (x, y)) if len(d) < 50 else None
    primary = "Pearson" if normal else "Spearman"
    return {"x": x, "y": y, "n": int(len(d)),
            "pearson_r": round(float(pr[0]), 3), "pearson_p": float(pr[1]),
            "spearman_rho": round(float(sr[0]), 3), "spearman_p": float(sr[1]),
            "normal": normal, "primary": primary}


# ---------------------------------------------------------------------------
# Step 4 结果文字生成（只做客观描述层）
# ---------------------------------------------------------------------------

def describe_test(t):
    """把检验结果 dict 转为论文"结果"章节风格的一句话（客观描述）。"""
    if t["method"] is None or t["p"] is None:
        return f"{t['comparison']}：{t['method']}"
    sig = "差异具有统计学意义" if t["p"] < 0.05 else "差异无统计学意义"
    effect = f"，{t['effect']}" if t["effect"] else ""
    posthoc = f"；事后检验建议：{t['posthoc']}" if t.get("posthoc") else ""
    return (f"对 {t['comparison']} 采用{t['method']}，结果为 {t['stat']}，"
            f"p{_fmt_p(t['p'])}，{sig}{effect}{posthoc}（n={t['n_total']}）。")


def describe_corr(c):
    if c is None:
        return ""
    primary_stat = (f"r={c['pearson_r']}, p{_fmt_p(c['pearson_p'])}"
                    if c["primary"] == "Pearson"
                    else f"ρ={c['spearman_rho']}, p{_fmt_p(c['spearman_p'])}")
    direction = "正相关" if (c["pearson_r"] if c["primary"] == "Pearson" else c["spearman_rho"]) > 0 else "负相关"
    note = "" if c["primary"] == "Pearson" else "（变量不满足正态性，以 Spearman 为准）"
    return (f"{c['x']} 与 {c['y']} 的{c['primary']}相关分析显示两变量呈显著{direction}："
            f"{primary_stat}（n={c['n']}）{note}。")


# ---------------------------------------------------------------------------
# 智能路径识别：二分类预测数据（y_true + y_score/y_pred）
# ---------------------------------------------------------------------------

def detect_binary_classification(df):
    """识别二分类预测结果表：存在 0/1 标签列 + 概率/预测列。

    返回 dict 或 None：{label_col, score_col?, pred_col?, model_col?}
    """
    cols = list(df.columns)
    label_col = score_col = pred_col = model_col = None
    for c in cols:
        lc = str(c).lower()
        vals = df[c].dropna()
        if label_col is None and set(vals.unique()) <= {0, 1} and len(vals) > 10:
            if lc in ("y_true", "label", "y", "true", "target", "ground_truth", "y_test") or "true" in lc or "label" in lc:
                label_col = c
                continue
        if score_col is None and pd.api.types.is_numeric_dtype(df[c]) and vals.between(0, 1).all() and df[c].nunique() > 5:
            if "score" in lc or "prob" in lc or "pred" in lc:
                score_col = c
                continue
        if pred_col is None and set(vals.unique()) <= {0, 1} and ("pred" in lc and "score" not in lc):
            pred_col = c
        if model_col is None and not pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() <= 8 and df[c].nunique() > 0:
            if "model" in lc or "method" in lc or "clf" in lc:
                model_col = c
    if label_col is None:
        return None
    return {"label_col": label_col, "score_col": score_col,
            "pred_col": pred_col, "model_col": model_col}


# ---------------------------------------------------------------------------
# Step 5 报告汇总
# ---------------------------------------------------------------------------

def run_autoreport(csv_path, group=None, value=None, x=None, y=None,
                   out_dir=None, yes=False):
    """主流程。返回报告路径与全部中间产物路径。"""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)

    print(f"=" * 62)
    print(f"AutoReport 一键分析：{csv_path}")
    print(f"数据 {df.shape[0]} 行 × {df.shape[1]} 列")
    print("=" * 62)

    # ---- Step 1 质量检查 ----
    quality = check_data_quality(df)
    print("\n[Step 1] 数据质量检查")
    if quality["issues"]:
        for i in quality["issues"]:
            print("  ⚠", i)
    else:
        print("  ✓ 未发现缺失>20%、明显离群等风险项")

    # ---- Step 2 智能推荐 ----
    recs = recommend_charts(df)
    print("\n[Step 2] 智能图表推荐")
    for i, r in enumerate(recs, 1):
        print(f"  {i}. {r['template']}" + (f"({r['x']}~{r['y']})" if r["x"] else "")
              + f" —— {r['reason']}")

    # 指定列优先；未指定则取推荐第 1 条
    chosen = None
    if group and value:
        chosen = {"template": "grouped_bar", "x": group, "y": value}
    elif x and y:
        chosen = {"template": "scatter_fit", "x": x, "y": y}
    elif recs:
        r0 = recs[0]
        chosen = {"template": r0["template"], "x": r0.get("x"), "y": r0.get("y")}

    if not yes:
        print("\n[提示] 当前为推荐模式，未执行出图。加 --yes 按推荐自动执行全部步骤；")
        print("       或用 --group/--value（组间比较）、--x/--y（相关分析）指定分析目标。")
        return {"report": None, "recommendations": recs, "quality": quality}

    # ---- Step 3 自动出图（复用模板与配方存档）----
    print("\n[Step 3] 自动出图")
    fig_paths = []
    captions = []
    pt._setup_style()

    # 路径A：二分类预测数据 → ROC + PR + 混淆矩阵套装
    binary = detect_binary_classification(df)
    if binary and binary["score_col"] and (yes and not group and not value and not x and not y):
        print("  [路径] 检测到二分类预测数据，自动执行分类评估套装")
        if binary["model_col"]:
            r = pt.roc_curves(df, label_col=binary["label_col"], score_col=binary["score_col"],
                              model_col=binary["model_col"],
                              save_path=out_dir / "fig1_roc_curves.png")
            fig_paths += r["paths"]
            auc_line = "、".join(f"{k} AUC={v['auc']}" for k, v in r["models"].items())
            test_text = f"分类评估：{auc_line}。"
            r2_ = pt.pr_curves(df, label_col=binary["label_col"], score_col=binary["score_col"],
                               model_col=binary["model_col"],
                               save_path=out_dir / "fig2_pr_curves.png")
            fig_paths += r2_["paths"]
            # 混淆矩阵：用第一个模型或全量
            m0 = list(pd.unique(df[binary["model_col"]].dropna()))[0] if binary["model_col"] else None
            sub = df[df[binary["model_col"]] == m0] if m0 else df
            pred_col = binary["pred_col"]
            if pred_col is None:  # 无预测列时按0.5阈值二值化
                sub = sub.assign(**{f"y_pred": (sub[binary["score_col"]] >= 0.5).astype(int)})
                pred_col = "y_pred"
            r3_ = pt.confusion_matrix(sub, true_col=binary["label_col"], pred_col=pred_col,
                                      normalize=True, title=f"{m0 or '模型'}混淆矩阵（行归一化）",
                                      save_path=out_dir / "fig3_confusion_matrix.png")
            fig_paths += r3_["paths"]
            test_text += f"{m0 or '模型'}总体准确率 {r3_['accuracy']}。"
            print(f"  ✓ ROC/PR/混淆矩阵套装（{len(fig_paths)} 个文件）")
            chosen = None  # 已处理，跳过通用路径
        else:
            chosen = None
            print("  - 检测到二分类数据但未检测到模型列，建议指定 --group/--value 手动分析")
    elif chosen:
        t = chosen["template"]
        if t == "grouped_bar":
            # 组间比较四件套（v1.3 创新④）：柱状+显著性 / 小提琴 / Q-Q / 三线表
            r = pt.grouped_bar(df, x=chosen["x"], y=chosen["y"],
                               save_path=out_dir / "fig1_grouped_bar.png")
            fig_paths += r["paths"]
            print("  ✓ 图1：", t)
            try:
                rv = pt.violin(df, x=chosen["x"], y=chosen["y"],
                               save_path=out_dir / "fig2_violin.png")
                fig_paths += rv["paths"]
                if rv.get("caption"):
                    captions.append(rv["caption"])
                print("  ✓ 图2： violin（含显著性标注）")
            except Exception as e:
                print("  - violin 跳过：", e)
            try:
                rq = pt.qq_plot(df, y=chosen["y"], group=chosen["x"],
                                save_path=out_dir / "fig3_qq_plot.png")
                fig_paths += rq["paths"]
                print("  ✓ 图3： qq_plot（前提检验可视化）")
            except Exception as e:
                print("  - qq_plot 跳过：", e)
            try:
                agg = df.groupby(chosen["x"], observed=True)[chosen["y"]].agg(["mean", "std", "count"]).reset_index()
                tbl = pd.DataFrame({
                    f"{chosen['x']}": agg[chosen["x"]].astype(str),
                    f"{chosen['y']}(均值±标准差)": agg.apply(
                        lambda r: f"{r['mean']:.2f}±{r['std']:.2f}", axis=1),
                    "样本量 n": agg["count"],
                })
                from three_line_table import df_to_three_line_table
                df_to_three_line_table(tbl,
                                       caption=f"表1 各{chosen['x']}的{chosen['y']}描述统计",
                                       note="注：数据以均值±标准差表示；n 为样本量。",
                                       save_path=out_dir / "表1_描述统计.docx")
                print("  ✓ 表1： 三线表（描述统计）")
            except Exception as e:
                print("  - 三线表跳过：", e)
        elif t == "grouped_box":
            r = pt.grouped_box(df, x=chosen["x"], y=chosen["y"],
                               save_path=out_dir / "fig1_grouped_box.png")
            fig_paths += r["paths"]
            print("  ✓ 图1：", t)
        elif t == "scatter_fit":
            r = pt.scatter_fit(df, x=chosen["x"], y=chosen["y"],
                               save_path=out_dir / "fig1_scatter_fit.png")
            fig_paths += r["paths"]
            print("  ✓ 图1：", t)
        elif t == "plot_line":
            gcol = group or next((c for c in df.columns
                                  if not pd.api.types.is_numeric_dtype(df[c])), None)
            r = pt.plot_line(df, x=chosen["x"], y=chosen["y"], group=gcol,
                             save_path=out_dir / "fig1_plot_line.png")
            fig_paths += r["paths"]
            print("  ✓ 图1：", t)
        elif t == "heatmap":
            r = pt.heatmap(df.corr(numeric_only=True),
                           save_path=out_dir / "fig1_heatmap.png")
            fig_paths += r["paths"]
            print("  ✓ 图1：", t)
        else:
            print("  ✓ 图1：", t)

    # ---- Step 4 自动统计检验 ----
    print("\n[Step 4] 自动统计检验（按决策表）")
    binary_path_taken = bool(binary and binary["score_col"] and binary["model_col"]
                             and yes and not group and not value and not x and not y)
    test_result, test_text = (None, "")
    corr_result, corr_text = None, ""
    if not binary_path_taken:
        if chosen and chosen.get("x") and chosen.get("y"):
            if not pd.api.types.is_numeric_dtype(df[chosen["x"]]):
                test_result = auto_group_test(df, chosen["x"], chosen["y"])
                test_text = describe_test(test_result)
            elif pd.api.types.is_numeric_dtype(df[chosen["y"]]):
                corr_result = auto_correlation(df, chosen["x"], chosen["y"])
                corr_text = describe_corr(corr_result)
    if test_text:
        print("  ✓", test_text)
    if corr_text:
        print("  ✓", corr_text)
    if not test_text and not corr_text and not binary_path_taken:
        print("  - 未找到可自动检验的数值列组合")

    # ---- Step 5 报告落盘 ----
    report_path = out_dir / "分析报告.md"
    lines = ["# 数据分析报告（AutoReport 自动生成）", "",
             f"- 数据文件：`{Path(csv_path).name}`（{df.shape[0]} 行 × {df.shape[1]} 列）",
             "- 生成方式：academic-research 技能 AutoReport 模块",
             "- 声明：本报告的统计量均由真实数据计算；结论解释权归作者；"
             "如用于论文，请核对图表并补充实验背景。", "",
             "## 1 数据质量检查", ""]
    if quality["issues"]:
        lines += [f"- ⚠ {i}" for i in quality["issues"]]
    else:
        lines.append("- 未发现缺失比例>20% 的列；离群值仅标记未删除。")
    lines += ["", "## 2 描述统计", "",
              "| 变量 | n | 缺失/% | 均值 | 标准差 | 最小 | 最大 |",
              "|---|---|---|---|---|---|---|"]
    for col, info in quality["columns"].items():
        if "mean" in info:
            lines.append(f"| {col} | {quality['n_rows']} | {info['missing_pct']} | "
                         f"{info['mean']} | {info['std']} | {info['min']} | {info['max']} |")
    lines += ["", "## 3 图表", ""]
    for p in fig_paths:
        lines.append(f"![{Path(p).stem}](./{Path(p).name})（{Path(p).name}）")
    for cap in captions:
        lines.append(f"- 图注建议：{cap}")
    tbl = out_dir / "表1_描述统计.docx"
    if tbl.exists():
        lines.append(f"- 描述统计三线表：`表1_描述统计.docx`")
    if test_text or corr_text:
        lines += ["", "## 4 统计检验结果", ""]
        if test_text:
            lines.append(test_text)
        if corr_text:
            lines.append(corr_text)
    lines += ["", "## 5 使用说明", "",
              "- 图表由 `plot_templates.py` 模板生成，同目录 `.recipe.json` 为绘图配方（可复现）；",
              "- 统计方法依据《数据分析可视化指南》第 2 节决策表自动选择；",
              "- 建议作者复核：前提检验细节、事后检验执行、以及结论的学科解释。", ""]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[Step 5] 报告已生成 → {report_path}")
    result = {"report": report_path, "figures": fig_paths,
              "test": test_result, "correlation": corr_result,
              "quality": quality, "recommendations": recs}
    if binary_path_taken:
        result["binary"] = binary
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSV 一键分析报告（AutoReport）")
    ap.add_argument("csv", help="输入 CSV 文件路径")
    ap.add_argument("--group", default=None, help="组间比较：分组列名（类别）")
    ap.add_argument("--value", default=None, help="组间比较：数值列名")
    ap.add_argument("--x", default=None, help="相关分析：自变量列名（连续）")
    ap.add_argument("--y", default=None, help="相关分析：因变量列名（连续）")
    ap.add_argument("--out", default=None, help="输出目录（默认 .temp/autoreport/）")
    ap.add_argument("--yes", action="store_true", help="全自动执行（默认只出推荐）")
    args = ap.parse_args(argv)
    run_autoreport(args.csv, group=args.group, value=args.value,
                   x=args.x, y=args.y, out_dir=args.out, yes=args.yes)


if __name__ == "__main__":
    main(sys.argv[1:])
