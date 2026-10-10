# -*- coding: utf-8 -*-
"""
plot_templates.py — 学术出图模板脚本（academic-research 技能 v1.3）

十二类高频学术图表的参数化模板，自动套用本技能 assets/academic.mplstyle 学术样式：
  - grouped_bar : 分组柱状图 + 误差线（均值±SD/SE 自动计算）
  - grouped_box : 分组箱线图（展示分布与离群值）
  - scatter_fit : 散点图 + 线性/二次拟合（自动报告 Pearson/Spearman 相关）
  - heatmap     : 相关矩阵热力图（标注相关系数）
  - plot_line   : 折线/训练曲线（多组趋势 + 最优点自动标注）
  - violin      : 小提琴图（分布形态 + 内嵌箱线）
  - qq_plot     : Q-Q 图（正态性诊断，决策表的可视化证据）
  - roc_curves  : ROC 曲线（多模型对比 + 自动 AUC + 随机基线）
  - pr_curves   : PR 曲线（不平衡数据分类评估 + 自动 AP）
  - confusion_matrix : 混淆矩阵（归一化/计数标注）
  - radar       : 雷达图（多指标模型对比，≤8 指标）
  - line_band   : 误差带折线（多 seed 训练曲线 mean±std 半透明带）

设计原则：
  1. 样式自动定位：根据本脚本所在位置回溯技能根目录，与安装路径无关（修复 v1.0 硬编码路径问题）
  2. 中文字体自动兜底：向当前字体族追加**本机实际存在**的中文字体
  3. 无界面安全：强制 Agg 后端，任何环境可运行
  4. 数据诚实：误差线、相关系数、AUC 等均由真实输入计算，不在图内虚构数值
  5. 统计规范内置：显著性标注自动选方法（正态→t，非正态→Mann-Whitney）
  6. 通用能力：save_pdf 矢量输出、绘图配方存档、风格预设（journal/thesis/colorblind）

快速验证：python plot_templates.py --demo  （用 samples/ 数据生成示例图）
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面环境安全
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

try:
    from scipy import stats as sps  # 用于相关与显著性，缺失时优雅降级
except Exception:  # pragma: no cover
    sps = None

# ---------------------------------------------------------------------------
# 样式与环境准备
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
MPLSTYLE = SKILL_ROOT / "assets" / "academic.mplstyle"
DEFAULT_OUT = Path(".temp") / "plots"


def _setup_style():
    """加载学术样式；样式文件缺失时降级为 matplotlib 默认样式并给出提示。"""
    if MPLSTYLE.exists():
        plt.style.use(str(MPLSTYLE))
    else:
        print(f"[warn] 未找到学术样式 {MPLSTYLE}，使用默认样式")
    # 中文字体兜底（分两步）：
    # 1) 向 serif / sans-serif 字体族追加**本机实际存在**的中文字体（避免 findfont 警告刷屏）
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    zh_candidates = ["SimHei", "Microsoft YaHei", "SimSun", "Noto Sans CJK SC",
                     "WenQuanYi Micro Hei", "Microsoft JhengHei", "KaiTi"]
    zh_fonts = [f for f in zh_candidates if f in available]
    for key in ("font.serif", "font.sans-serif"):
        try:
            current = list(matplotlib.rcParams[key])
            matplotlib.rcParams[key] = current + [f for f in zh_fonts if f not in current]
        except KeyError:
            pass
    # 2) 关键：matplotlib 的逐字形回退仅在 font.family 为具体字体列表时生效；
    #    样式文件设置的是通用别名（serif），此处展开为具体列表，否则中文渲染为方框
    fam = matplotlib.rcParams["font.family"]
    if isinstance(fam, str):
        fam = [fam]
    resolved = []
    for f in fam:
        if f in ("serif", "sans-serif", "monospace", "cursive", "fantasy"):
            try:
                resolved.extend(list(matplotlib.rcParams[f"font.{f}"]))
            except KeyError:
                pass
        else:
            resolved.append(f)
    dedup = []
    for f in resolved:
        if f not in dedup:
            dedup.append(f)
    matplotlib.rcParams["font.family"] = dedup
    matplotlib.rcParams["axes.unicode_minus"] = False


def _ensure_dir(save_path: Path) -> Path:
    save_path.parent.mkdir(parents=True, exist_ok=True)
    return save_path


def _resolve_save_path(save_path=None, default_name="fig.png") -> Path:
    if save_path is None:
        out = DEFAULT_OUT / default_name
    else:
        out = Path(save_path)
    return _ensure_dir(out)


def _save_fig(fig, save_path, save_pdf=False):
    """统一保存出口：PNG（300 DPI）+ 可选同名 PDF 矢量版；返回实际保存的路径列表。

    期刊投稿场景建议 save_pdf=True：矢量图缩放不失真，且样式文件已配置
    pdf.fonttype=42（TrueType），避免 Type 3 字体被期刊拒收。
    """
    paths = []
    out = _resolve_save_path(save_path, "fig.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    paths.append(out)
    if save_pdf:
        pdf_out = out.with_suffix(".pdf")
        fig.savefig(pdf_out, bbox_inches="tight")
        paths.append(pdf_out)
    plt.close(fig)
    return paths


def _save_recipe(template, params, paths, data=None):
    """绘图配方存档：模板名/参数/数据指纹落盘 JSON，便于复现与论文返修时同步。

    数据指纹取传入数据的行数+关键列哈希（不存数据本体，避免隐私与体积问题）。
    """
    try:
        import hashlib
        import json
        recipe = {
            "template": template,
            "params": {k: (str(v) if isinstance(v, Path) else v)
                       for k, v in params.items() if k not in ("df",)},
            "outputs": [str(p) for p in paths],
            "created": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        if data is not None:
            try:
                fp = hashlib.md5(
                    pd.util.hash_pandas_object(data, index=True).values.tobytes()
                ).hexdigest()
                recipe["data_fingerprint"] = {"rows": int(len(data)), "md5": fp}
            except Exception:
                recipe["data_fingerprint"] = {"rows": int(len(data))}
        out = Path(paths[0]).with_suffix(".recipe.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(recipe, f, ensure_ascii=False, indent=2)
        return out
    except Exception as e:  # 配方存档失败不阻断主流程
        print(f"[warn] 绘图配方存档失败：{e}")
        return None


def _sig_stars(p):
    if p is None:
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


# ---------------------------------------------------------------------------
# 风格预设（v1.3 创新③）
# ---------------------------------------------------------------------------

STYLE_PRESETS = {
    # 中文期刊常用：黑白灰 + 线型/填充纹理区分（黑白打印友好）
    "journal": {
        "colors": ["000000", "555555", "999999", "333333", "777777", "BBBBBB"],
    },
    # 学位论文/演示：彩色（沿用学术色板）
    "thesis": {
        "colors": ["000000", "E0342D", "2E5B9F", "0B8A6D", "B95C00", "8C4BA0"],
    },
    # 色盲友好（避红绿组合，Okabe-Ito 色板）
    "colorblind": {
        "colors": ["000000", "E69F00", "0072B2", "009E73", "CC79A7", "56B4E9", "F0E442", "D55E00"],
    },
}


def set_style_preset(preset="thesis"):
    """一键切换风格预设：journal（黑白期刊）/ thesis（彩色学位论文）/ colorblind（色盲友好）。

    在模板调用前执行一次即可，后续所有模板生效。
    """
    import matplotlib as _mpl
    from cycler import cycler as _c  # matplotlib 自带依赖
    p = STYLE_PRESETS.get(preset)
    if p is None:
        print(f"[warn] 未知预设 {preset}，可选：{'/'.join(STYLE_PRESETS)}")
        return
    _mpl.rcParams["axes.prop_cycle"] = _c(color=["#" + c for c in p["colors"]])
    print(f"[style] 已切换风格预设：{preset}")


# ---------------------------------------------------------------------------
# 自动显著性标注（v1.3 创新①）
# ---------------------------------------------------------------------------

def _pairwise_tests(df, x, y, groups):
    """组间两两检验：正态→t，非正态→Mann-Whitney（与指南第 2 节决策表一致）。

    返回 [(组A, 组B, p), ...]。
    """
    pairs = []
    keys = list(groups)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = df[df[x] == keys[i]][y].dropna().values
            b = df[df[x] == keys[j]][y].dropna().values
            if len(a) < 2 or len(b) < 2 or sps is None:
                continue
            normal = (sps.shapiro(a)[1] > 0.05 and sps.shapiro(b)[1] > 0.05
                      if (len(a) < 50 and len(b) < 50) else True)
            if normal:
                _, p = sps.ttest_ind(a, b)
            else:
                _, p = sps.mannwhitneyu(a, b)
            pairs.append((keys[i], keys[j], float(p)))
    return pairs


def _annotate_significance(ax, pairs, level_positions, y_max, y_span, start_h=0.94, step_h=0.055):
    """在坐标轴上画两两显著性星号横线。level_positions: {组名: x 位置}。"""
    annotated = 0
    for ga, gb, p in pairs:
        stars = _sig_stars(p)
        if stars in ("", "ns") and p >= 0.05:
            continue  # 只标显著的
        xa, xb = level_positions[ga], level_positions[gb]
        h = y_max + y_span * (start_h - 0.85 + annotated * step_h)
        ax.plot([xa, xa, xb, xb], [h - y_span * 0.008, h, h, h - y_span * 0.008],
                lw=0.9, color="black")
        ax.text((xa + xb) / 2, h + y_span * 0.004, stars if stars != "ns" else "ns",
                ha="center", va="bottom", fontsize=9)
        annotated += 1
    return annotated


# ---------------------------------------------------------------------------
# 图注自动生成（v1.3 创新⑤）
# ---------------------------------------------------------------------------

def make_caption(template, *, x=None, y=None, group=None, stats=None, n=None,
                 yerr=None, caption_label="图"):
    """生成规范图注文字（随图返回，可直接用于论文排版）。

    示例：图1 各模型测试准确率比较（x̄±s, n=5；组间比较采用独立样本t检验，* p<0.05）
    """
    parts = []
    subject = f"{y}" + (f" 按 {group} 分组" if group else "") + (f" 随 {x} 变化" if x and template in ("scatter_fit", "plot_line", "line_band") else f" 在各 {x} 组间比较")
    if template == "roc_curves":
        subject = "受试者工作特征（ROC）曲线"
    elif template == "pr_curves":
        subject = "查准率-查全率（PR）曲线"
    elif template == "confusion_matrix":
        subject = "分类混淆矩阵"
    elif template == "qq_plot":
        subject = f"{y} 的正态性 Q-Q 图"
    elif template == "radar":
        subject = "多指标综合性能对比"
    elif template == "heatmap":
        subject = "变量相关矩阵"
    parts.append(subject)
    detail = []
    if n is not None:
        detail.append(f"n={n}")
    if yerr in ("std", "se"):
        detail.append("x̄±s" if yerr == "std" else "x̄±SE")
    if stats:
        detail.append(f"检验方法：{stats}")
    tail = "；".join(detail)
    return f"{caption_label} {subject}（{tail}）" if tail else f"{caption_label} {subject}"


# ---------------------------------------------------------------------------
# 模板 1：分组柱状图 + 误差线
# ---------------------------------------------------------------------------

def grouped_bar(df, x, y, group=None, yerr="std", *, xlabel=None, ylabel=None,
                title=None, save_path=None, capsize=3, save_pdf=False):
    """分组柱状图（长表输入，均值±误差线自动聚合）。

    参数
    ----
    df : pandas.DataFrame，长表（每行一次观测）
    x  : 类别轴列名（如 dataset）
    y  : 数值列名（如 accuracy）
    group : 分组列名（如 model）；None 时单组
    yerr : "std"（标准差）/"se"（标准误）/ None（不画误差线）

    返回
    ----
    dict：{"save_path": Path, "table": DataFrame(聚合结果，含 mean/std/se/count)}
    """
    agg = df.groupby([x] + ([group] if group else []), observed=True)[y].agg(["mean", "std", "count"])
    agg["se"] = agg["std"] / np.sqrt(agg["count"].clip(lower=1))
    err_col = {"std": "std", "se": "se"}.get(yerr, None)

    fig, ax = plt.subplots()
    if group:
        piv = agg["mean"].unstack(group)  # 行=x, 列=group
        errs = agg[err_col].unstack(group) if err_col else None
        xs = np.arange(len(piv.index))
        w = 0.8 / max(len(piv.columns), 1)
        for i, col in enumerate(piv.columns):
            kw = {}
            if errs is not None:
                kw = {"yerr": errs[col].values, "capsize": capsize}
            ax.bar(xs + i * w - 0.4 + w / 2, piv[col].values, width=w, label=str(col), **kw)
        ax.set_xticks(xs)
        ax.set_xticklabels([str(v) for v in piv.index])
        ax.legend()
    else:
        piv = agg["mean"]
        errs = agg[err_col] if err_col else None
        xs = np.arange(len(piv.index))
        ax.bar(xs, piv.values, width=0.6,
               yerr=(errs.values if errs is not None else None), capsize=capsize)
        ax.set_xticks(xs)
        ax.set_xticklabels([str(v) for v in piv.index])

    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("grouped_bar", {"x": x, "y": y, "group": group, "yerr": yerr,
                                 "xlabel": xlabel, "ylabel": ylabel}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "table": agg.reset_index()}


# ---------------------------------------------------------------------------
# 模板 2：分组箱线图
# ---------------------------------------------------------------------------

def grouped_box(df, x, y, group=None, *, xlabel=None, ylabel=None, title=None,
                save_path=None, show_outliers=True, save_pdf=False):
    """分组箱线图（长表输入，展示分布/中位数/离群值，适合非正态数据）。

    有 group 时采用"位置分组"布局：x 轴只放类别（如 dataset），每个类别下按
    group 并排多个箱体，group 用颜色+图例区分（学术出版标准画法），
    避免长组合标签在横轴重叠。
    """
    fig, ax = plt.subplots()
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = ([c["color"] for c in list(cycle)[:8]] if cycle
               else ["C0", "C1", "C2", "C3"])
    x_cats = list(pd.unique(df[x].dropna()))

    def _box(values, positions, width, color):
        """画一组箱体并统一上色；兼容无 manage_ticks 参数的旧版 matplotlib。"""
        try:
            bp = ax.boxplot(values, positions=positions, widths=width,
                            patch_artist=True, showfliers=show_outliers,
                            manage_ticks=False)
        except TypeError:  # matplotlib < 3.9
            bp = ax.boxplot(values, positions=positions, widths=width,
                            patch_artist=True, showfliers=show_outliers)
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        for element in ("whiskers", "caps", "medians"):
            for line in bp.get(element, []):
                line.set_color("black")

    if group:
        g_cats = list(pd.unique(df[group].dropna()))
        width = 0.8 / max(len(g_cats), 1)
        handles = []
        for gi, g in enumerate(g_cats):
            values, positions = [], []
            for xi, xc in enumerate(x_cats):
                sub = df[(df[x] == xc) & (df[group] == g)][y].dropna().values
                values.append(sub)
                positions.append(xi - 0.4 + width / 2 + gi * width)
            color = palette[gi % len(palette)]
            _box(values, positions, width * 0.85, color)
            handles.append(mpatches.Patch(facecolor=color, alpha=0.7, label=str(g)))
        ax.set_xticks(range(len(x_cats)))
        ax.set_xticklabels([str(v) for v in x_cats])
        ax.legend(handles=handles)
    else:
        values = [df[df[x] == xc][y].dropna().values for xc in x_cats]
        _box(values, list(range(len(x_cats))), 0.55, palette[0])
        ax.set_xticks(range(len(x_cats)))
        ax.set_xticklabels([str(v) for v in x_cats])

    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("grouped_box", {"x": x, "y": y, "group": group,
                                 "xlabel": xlabel, "ylabel": ylabel}, paths, data=df)
    return {"save_path": paths[0], "paths": paths}


# ---------------------------------------------------------------------------
# 模板 3：散点图 + 拟合线（自动报告相关系数）
# ---------------------------------------------------------------------------

def scatter_fit(df, x, y, fit="linear", *, xlabel=None, ylabel=None, title=None,
                save_path=None, annotate_stats=True, save_pdf=False):
    """散点图 + 拟合线。

    fit : "linear"（一次）/ "quadratic"（二次）/ "none"（仅散点）
    返回 dict：save_path 与统计结果（Pearson r/p、Spearman rho/p、拟合系数）。
    """
    d = df[[x, y]].dropna()
    xs, ys = d[x].to_numpy(dtype=float), d[y].to_numpy(dtype=float)

    fig, ax = plt.subplots()
    ax.scatter(xs, ys, s=28, alpha=0.85, edgecolors="none")

    stats_out = {}
    if len(xs) >= 3:
        if sps is not None:
            pr = sps.pearsonr(xs, ys)
            sr = sps.spearmanr(xs, ys)
            stats_out["pearson_r"], stats_out["pearson_p"] = float(pr[0]), float(pr[1])
            stats_out["spearman_rho"], stats_out["spearman_p"] = float(sr[0]), float(sr[1])
        deg = {"linear": 1, "quadratic": 2, "none": None}.get(fit)
        if deg:
            coef = np.polyfit(xs, ys, deg)
            xs_line = np.linspace(xs.min(), xs.max(), 200)
            ax.plot(xs_line, np.polyval(coef, xs_line), lw=1.5)
            terms = []
            for i, c in enumerate(coef):
                power = deg - i
                if power > 1:
                    terms.append(f"{c:+.4g}x^{power}")
                elif power == 1:
                    terms.append(f"{c:+.4g}x")
                else:
                    terms.append(f"{c:+.4g}")
            stats_out["fit"] = " ".join(terms)
        if annotate_stats and "pearson_r" in stats_out:
            r, p = stats_out["pearson_r"], stats_out["pearson_p"]
            ax.annotate(f"Pearson r = {r:.3f}{_sig_stars(p)}",
                       xy=(0.98, 0.02), xycoords="axes fraction",
                       ha="right", va="bottom", fontsize=9)
    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("scatter_fit", {"x": x, "y": y, "fit": fit,
                                 "xlabel": xlabel, "ylabel": ylabel}, paths, data=df)
    stats_out["save_path"] = paths[0]
    stats_out["paths"] = paths
    return stats_out


# ---------------------------------------------------------------------------
# 模板 4：相关矩阵热力图
# ---------------------------------------------------------------------------

def heatmap(df, *, cmap="RdBu_r", vmin=None, vmax=None, annot=True, fmt=".2f",
            title=None, save_path=None, cbar_label="相关系数 r", save_pdf=False):
    """相关矩阵热力图。df 传入数值矩阵（或先 df.corr()）。

    vmin/vmax 缺省时自动判断：数值双向分布 → (-1, 1) 对称量程；否则按数据范围。
    """
    fig, ax = plt.subplots()
    m = df.to_numpy(dtype=float)
    if vmin is None and vmax is None:
        if m.min() < -0.1 and m.max() > 0.1:  # 疑似相关矩阵 → 对称量程
            vmin, vmax = -1, 1
        else:
            vmin, vmax = float(m.min()), float(m.max())
    im = ax.imshow(m, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(df.columns)))
    ax.set_xticklabels(df.columns, rotation=35, ha="right")
    ax.set_yticks(range(len(df.index)))
    ax.set_yticklabels(df.index)
    if annot:
        span = max(abs(vmin), abs(vmax))
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m[i, j]
                color = "white" if abs(v) >= 0.75 * span else "black"
                ax.text(j, i, f"{v:{fmt}}", ha="center", va="center", fontsize=8.5, color=color)
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label(cbar_label)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("heatmap", {"cmap": cmap, "annot": annot, "title": title}, paths, data=df)
    return {"save_path": paths[0], "paths": paths}


# ---------------------------------------------------------------------------
# 模板 5：折线图 / 训练曲线（多组趋势 + 最优点自动标注）
# ---------------------------------------------------------------------------

def plot_line(df, x, y, group=None, *, xlabel=None, ylabel=None, title=None,
               save_path=None, marker_every=None, best="max", annotate_best=True,
               save_pdf=False):
    """折线图 / 训练曲线（长表输入，适合 loss、accuracy 随 epoch 变化等趋势数据）。

    参数
    ----
    group : 分组列名（如 model / method）；None 时单条线
    marker_every : 每隔几个点画一次标记（默认自动：点密时隔点，避免标记重叠）
    best : "max"（标注最大值，如 accuracy）/ "min"（标注最小值，如 loss）
    annotate_best : True 时每组自动标注最优点的坐标（虚线引导 + 数值）

    返回 dict：save_path / paths / best（各组最优值与位置）
    """
    fig, ax = plt.subplots()
    groups = list(pd.unique(df[group].dropna())) if group else [None]
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else None
    markers = ["o", "s", "^", "D", "v", "P", "X", "*"]
    best_out = {}

    total_x = len(pd.unique(df[x].dropna()))
    if marker_every is None:
        marker_every = max(1, total_x // 10)  # 点数多时隔点画标记

    for gi, g in enumerate(groups):
        sub = (df[df[group] == g] if group else df)[[x, y]].dropna().sort_values(x)
        xs, ys = sub[x].to_numpy(dtype=float), sub[y].to_numpy(dtype=float)
        kw = {"marker": markers[gi % len(markers)], "markevery": marker_every,
              "ms": 5, "lw": 1.5}
        if palette:
            kw["color"] = palette[gi % len(palette)]
        if g is not None:
            kw["label"] = str(g)
        line, = ax.plot(xs, ys, **kw)
        # 最优点标注
        idx = int(np.nanargmax(ys) if best == "max" else np.nanargmin(ys))
        best_out[str(g) if g is not None else y] = {"x": float(xs[idx]), "y": float(ys[idx])}
        if annotate_best:
            ax.annotate(f"{ys[idx]:.4g}", xy=(xs[idx], ys[idx]),
                        xytext=(0, 10), textcoords="offset points",
                        ha="center", fontsize=9, color=line.get_color())
            ax.plot([xs[idx], xs[idx]], [ax.get_ylim()[0], ys[idx]],
                    ls="--", lw=0.8, color=line.get_color(), alpha=0.45)
    if group:
        ax.legend()
    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("plot_line", {"x": x, "y": y, "group": group, "best": best,
                                 "xlabel": xlabel, "ylabel": ylabel}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "best": best_out}


# ---------------------------------------------------------------------------
# 模板 6：小提琴图（分布形态 + 内嵌箱线）
# ---------------------------------------------------------------------------

def violin(df, x, y, *, xlabel=None, ylabel=None, title=None,
           save_path=None, save_pdf=False, annotate_sig=True):
    """小提琴图：展示各组数值分布形态（带宽≈密度），内嵌迷你箱线。

    比 grouped_box 多表达"分布形状"（单峰/双峰/偏态），适合分布差异论证。
    annotate_sig=True 时自动做两两检验并画星号线（正态→t，非正态→Mann-Whitney）。
    """
    fig, ax = plt.subplots()
    cats = list(pd.unique(df[x].dropna()))
    data = [df[df[x] == c][y].dropna().values for c in cats]
    vp = ax.violinplot(data, positions=range(len(cats)), widths=0.7,
                       showmeans=False, showextrema=False)
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else ["C0", "C1", "C2"]
    for i, body in enumerate(vp["bodies"]):
        color = palette[i % len(palette)]
        body.set_facecolor(color)
        body.set_alpha(0.55)
        body.set_edgecolor("black")
        body.set_linewidth(0.8)
        # 内嵌迷你箱线
        q1, med, q3 = np.percentile(data[i], [25, 50, 75])
        ax.plot([i - 0.09, i + 0.09], [med, med], color="black", lw=1.8)
        ax.plot([i, i], [q1, q3], color="black", lw=1.0)
        ax.plot([i - 0.09, i + 0.09], [q1, q1], color="black", lw=1.0)
        ax.plot([i - 0.09, i + 0.09], [q3, q3], color="black", lw=1.0)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels([str(c) for c in cats])
    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    # 自动显著性标注
    n_sig = 0
    if annotate_sig and len(cats) >= 2 and sps is not None:
        pairs = _pairwise_tests(df, x, y, cats)
        all_vals = df[y].dropna()
        y_min, y_max = float(all_vals.min()), float(all_vals.max())
        y_span = max(y_max - y_min, 1e-9)
        ax.set_ylim(y_min - y_span * 0.08, y_max + y_span * 0.30)
        n_sig = _annotate_significance(ax, pairs, {c: i for i, c in enumerate(cats)},
                                       y_max, y_span)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("violin", {"x": x, "y": y, "annotate_sig": annotate_sig}, paths, data=df)
    caption = make_caption("violin", x=x, y=y, n=int(df.groupby(x, observed=True).size().sum()),
                           stats="两两比较见星号标注" if n_sig else None)
    return {"save_path": paths[0], "paths": paths, "n_significant_pairs": n_sig,
            "caption": caption}


# ---------------------------------------------------------------------------
# 模板 7：Q-Q 图（正态性诊断）
# ---------------------------------------------------------------------------

def qq_plot(df, y, group=None, *, save_path=None, save_pdf=False, title=None):
    """Q-Q 图：样本分位数 vs 理论正态分位数。点落在对角线上≈正态。

    group 指定时自动分子图（组数 >4 时自动换行，最多 4 列），并附
    Shapiro-Wilk 检验 p 值标注——统计前提检验的"可视化证据"，
    与指南第 2 节决策表联动。
    """
    import math
    if group:
        cats = list(pd.unique(df[group].dropna()))
        ncols = min(len(cats), 4)  # 超过 4 组自动换行，防止一行过宽
        nrows = math.ceil(len(cats) / ncols)
        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(4 * ncols, 3.9 * nrows),
                                 sharey=True, squeeze=False)
        flat = axes.flatten()
        for extra in flat[len(cats):]:  # 隐藏多余空位
            extra.set_visible(False)
        axes = flat[:len(cats)]
    else:
        cats = [None]
        fig, axes = plt.subplots(1, 1, figsize=(4.5, 4))
        axes = np.array([axes])
    results = {}
    for ax, g in zip(axes, cats):
        vals = (df[y].dropna() if g is None else df[df[group] == g][y].dropna()).to_numpy(dtype=float)
        vals = np.sort(vals)
        n = len(vals)
        if n < 3:
            continue
        probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
        theo = sps.norm.ppf(probs) if sps is not None else probs
        mean, std = vals.mean(), vals.std(ddof=1)
        ax.scatter(theo, (vals - mean) / std if std > 0 else vals, s=16, alpha=0.85)
        ax.plot([-3, 3], [-3, 3], ls="--", lw=1, color="gray")
        ax.set_xlim(-3.2, 3.2)
        ax.set_ylim(-3.2, 3.2)
        ax.set_xlabel("理论正态分位数")
        ax.set_ylabel("标准化样本分位数")
        label = str(g) if g is not None else str(y)
        p_val = float(sps.shapiro(vals)[1]) if (sps is not None and 3 <= n <= 5000) else None
        if p_val is not None:
            verdict = "近似正态" if p_val > 0.05 else "偏离正态"
            ax.set_title(f"{label}\nShapiro-Wilk p={p_val:.3f}（{verdict}）", fontsize=10)
        else:
            ax.set_title(label, fontsize=10)
        results[label] = {"n": int(n), "shapiro_p": round(p_val, 4) if p_val is not None else None,
                          "normal": bool(p_val is not None and p_val > 0.05)}
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("qq_plot", {"y": y, "group": group}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "groups": results}


# ---------------------------------------------------------------------------
# 模板 8：ROC 曲线（多模型 + 自动 AUC）
# ---------------------------------------------------------------------------

def roc_curves(df, label_col, score_col, model_col=None, *, save_path=None,
               save_pdf=False, title=None):
    """ROC 曲线：多模型对比 + 自动计算 AUC + 随机基线。

    df 长表：label_col（0/1 真实标签）、score_col（预测为正类的概率/分数）、
    model_col（模型名，多模型时分组）。
    """
    fig, ax = plt.subplots()
    models = list(pd.unique(df[model_col].dropna())) if model_col else [None]
    results = {}
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else ["C0", "C1", "C2"]
    for mi, m in enumerate(models):
        sub = df if m is None else df[df[model_col] == m]
        labels = sub[label_col].to_numpy(dtype=int)
        scores = sub[score_col].to_numpy(dtype=float)
        mask = ~np.isnan(scores)
        labels, scores = labels[mask], scores[mask]
        if len(labels) < 5:
            continue
        order = np.argsort(-scores)
        labels_sorted = labels[order]
        P, N = int(labels.sum()), int((1 - labels).sum())
        if P == 0 or N == 0:
            continue
        tpr = np.concatenate([[0], np.cumsum(labels_sorted) / P])
        fpr = np.concatenate([[0], np.cumsum(1 - labels_sorted) / N])
        auc = float(np.trapezoid(tpr, fpr)) if hasattr(np, "trapezoid") else float(np.trapz(tpr, fpr))
        color = palette[mi % len(palette)]
        name = str(m) if m is not None else "model"
        ax.plot(fpr, tpr, color=color, lw=1.5, label=f"{name} (AUC={auc:.3f})")
        results[name] = {"auc": round(auc, 4), "n": int(len(labels)),
                         "n_pos": P, "n_neg": N}
    ax.plot([0, 1], [0, 1], ls="--", lw=0.9, color="gray", label="随机基线 (AUC=0.5)")
    ax.set_xlabel("假正例率 FPR")
    ax.set_ylabel("真正例率 TPR")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right", fontsize=9)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("roc_curves", {"label_col": label_col, "score_col": score_col,
                                "model_col": model_col}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "models": results}


# ---------------------------------------------------------------------------
# 模板 9：PR 曲线（不平衡数据评估）
# ---------------------------------------------------------------------------

def pr_curves(df, label_col, score_col, model_col=None, *, save_path=None,
              save_pdf=False, title=None):
    """PR 曲线：查准率-查全率，不平衡数据（正类稀少）时比 ROC 更敏感。自动计算 AP。

    随机基线 = 全量数据的正类率 P(y=1)，与单模型数据的波动无关。
    """
    fig, ax = plt.subplots()
    models = list(pd.unique(df[model_col].dropna())) if model_col else [None]
    results = {}
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else ["C0", "C1", "C2"]
    # 随机基线：全量数据正类率（避免受遍历到的第一个模型影响）
    all_labels = df[label_col].dropna().to_numpy(dtype=int)
    base_rate = float(all_labels.mean()) if len(all_labels) else None
    for mi, m in enumerate(models):
        sub = df if m is None else df[df[model_col] == m]
        labels = sub[label_col].to_numpy(dtype=int)
        scores = sub[score_col].to_numpy(dtype=float)
        mask = ~np.isnan(scores)
        labels, scores = labels[mask], scores[mask]
        if len(labels) == 0 or labels.sum() == 0:
            continue
        order = np.argsort(-scores)
        labels_sorted = labels[order]
        P = int(labels.sum())
        tp = np.cumsum(labels_sorted)
        precision = tp / np.arange(1, len(labels) + 1)
        recall = tp / P
        precision = np.concatenate([[1.0], precision])
        recall = np.concatenate([[0.0], recall])
        ap = float(np.trapezoid(precision, recall)) if hasattr(np, "trapezoid") else float(np.trapz(precision, recall))
        color = palette[mi % len(palette)]
        name = str(m) if m is not None else "model"
        ax.plot(recall, precision, color=color, lw=1.5, label=f"{name} (AP={ap:.3f})")
        results[name] = {"ap": round(ap, 4), "n_pos": P}
    if base_rate is not None:
        ax.axhline(base_rate, ls="--", lw=0.9, color="gray",
                   label=f"随机基线 (P={base_rate:.3f})")
    ax.set_xlabel("查全率 Recall")
    ax.set_ylabel("查准率 Precision")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower left", fontsize=9)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("pr_curves", {"label_col": label_col, "score_col": score_col,
                               "model_col": model_col}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "models": results}


# ---------------------------------------------------------------------------
# 模板 10：混淆矩阵
# ---------------------------------------------------------------------------

def confusion_matrix(df, true_col, pred_col, *, normalize=True, save_path=None,
                     save_pdf=False, title=None, cmap="Blues"):
    """混淆矩阵：真实标签 × 预测标签。

    normalize=True 显示行归一化占比，False 显示计数。
    自动输出总体准确率与各类别 Precision/Recall/F1。
    """
    true = df[true_col].astype(str)
    pred = df[pred_col].astype(str)
    classes = sorted(set(true) | set(pred))
    idx = {c: i for i, c in enumerate(classes)}
    m = np.zeros((len(classes), len(classes)), dtype=float)
    for t, p in zip(true, pred):
        m[idx[t], idx[p]] += 1
    display = m / m.sum(axis=1, keepdims=True).clip(min=1) if normalize else m

    fig, ax = plt.subplots()
    im = ax.imshow(display, cmap=cmap, vmin=0,
                   vmax=display.max() if normalize else None)
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=35, ha="right")
    ax.set_yticklabels(classes)
    ax.set_xlabel(f"预测{pred_col}")
    ax.set_ylabel(f"真实{true_col}")
    thresh = display.max() * 0.6 if display.max() > 0 else 0.5
    for i in range(len(classes)):
        for j in range(len(classes)):
            txt = f"{int(m[i, j])}" if not normalize else f"{display[i, j]:.3f}"
            color = "white" if display[i, j] > thresh else "black"
            ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=color)
    if normalize:
        cb = fig.colorbar(im, ax=ax, shrink=0.85)
        cb.set_label("行归一化占比")
    if title:
        ax.set_title(title)
    report = {}
    for c in classes:
        i = idx[c]
        tp = m[i, i]
        fp = m[:, i].sum() - tp
        fn = m[i, :].sum() - tp
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
        report[c] = {"precision": round(precision, 4) if precision else None,
                     "recall": round(recall, 4) if recall else None,
                     "f1": round(f1, 4) if f1 else None}
    acc = float(np.trace(m) / m.sum()) if m.sum() else None
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("confusion_matrix", {"true_col": true_col, "pred_col": pred_col,
                                      "normalize": normalize}, paths, data=df)
    return {"save_path": paths[0], "paths": paths, "accuracy": round(acc, 4) if acc else None,
            "per_class": report, "confusion": m.tolist()}


# ---------------------------------------------------------------------------
# 模板 11：雷达图（多指标模型对比）
# ---------------------------------------------------------------------------

def radar(df, metrics=None, model_col=None, *, save_path=None, save_pdf=False,
          title=None, higher_is_better=None):
    """雷达图：多指标综合性能对比（指标数 3-10，建议 ≤8）。

    df 宽表：每行一个模型，各列为指标。metrics 指定参与对比的数值列；
    higher_is_better：{列名: True/False}，False 的指标（如时延）自动反向归一化；
    所有指标 min-max 归一到 [0,1]，不同量纲可比。
    """
    if model_col and model_col in df.columns:
        data = df.set_index(model_col)
    else:
        data = df
    if metrics is None:
        metrics = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
    metrics = [c for c in metrics if c in data.columns]
    if not (3 <= len(metrics) <= 10):
        raise ValueError(f"雷达图指标数需在 3-10 之间，当前 {len(metrics)}")
    higher_is_better = higher_is_better or {}

    norm = pd.DataFrame(index=data.index)
    for mcol in metrics:
        vals = data[mcol].astype(float)
        rng = vals.max() - vals.min()
        if rng <= 0:
            norm[mcol] = 1.0
        elif higher_is_better.get(mcol, True):
            norm[mcol] = (vals - vals.min()) / rng
        else:
            norm[mcol] = (vals.max() - vals) / rng
    norm = norm.clip(0, 1) * 0.9 + 0.05

    n = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig = plt.figure()
    ax = fig.add_subplot(111, polar=True)
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else ["C0", "C1", "C2"]
    for i, (label, row) in enumerate(norm.iterrows()):
        vals = row.tolist()
        vals += vals[:1]
        color = palette[i % len(palette)]
        ax.plot(angles, vals, lw=1.5, color=color, label=str(label))
        ax.fill(angles, vals, alpha=0.12, color=color)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=8)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.08), fontsize=9)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("radar", {"metrics": metrics, "model_col": model_col,
                            "higher_is_better": higher_is_better}, paths, data=df)
    return {"save_path": paths[0], "paths": paths}


# ---------------------------------------------------------------------------
# 模板 12：误差带折线（多 seed 训练曲线 mean±std）
# ---------------------------------------------------------------------------

def line_band(df, x, y, group=None, *, xlabel=None, ylabel=None, title=None,
              save_path=None, save_pdf=False, band=1.0, annotate_best=True):
    """误差带折线：多 seed 重复实验的 mean±band×std 半透明带。

    深度学习规范画法：单条线画训练曲线会被审稿人质疑未报告稳定性；
    此模板以均值主线 + 半透明带表达跨 seed 稳定性。
    df 长表：x（epoch）、y（指标）、group（模型），每个 (x, group) 下多个观测。
    """
    fig, ax = plt.subplots()
    agg = df.groupby([x] + ([group] if group else []), observed=True)[y].agg(["mean", "std"])
    cycle = plt.rcParams.get("axes.prop_cycle")
    palette = [c["color"] for c in list(cycle)[:8]] if cycle else ["C0", "C1", "C2"]
    stats_out = {}
    if group:
        for gi, g in enumerate(agg.index.get_level_values(group).unique()):
            sub = agg.xs(g, level=group)
            xs = sub.index.to_numpy(dtype=float)
            mean = sub["mean"].to_numpy(dtype=float)
            std = sub["std"].fillna(0).to_numpy(dtype=float)
            color = palette[gi % len(palette)]
            ax.plot(xs, mean, lw=1.5, color=color, label=str(g))
            ax.fill_between(xs, mean - band * std, mean + band * std,
                            alpha=0.18, color=color, linewidth=0)
            stats_out[str(g)] = {"final_mean": round(float(mean[-1]), 4),
                                 "final_std": round(float(std[-1]), 4) if std.size else None}
        ax.legend()
        if annotate_best:
            for gi, g in enumerate(agg.index.get_level_values(group).unique()):
                sub = agg.xs(g, level=group)
                means = sub["mean"].to_numpy(dtype=float)
                best_i = int(np.argmax(means))
                xval, yval = float(sub.index[best_i]), float(means[best_i])
                color = palette[gi % len(palette)]
                ax.annotate(f"{yval:.4g}", xy=(xval, yval), xytext=(0, 8),
                            textcoords="offset points", ha="center", fontsize=8.5, color=color)
    else:
        xs = agg.index.to_numpy(dtype=float)
        mean = agg["mean"].to_numpy(dtype=float)
        std = agg["std"].fillna(0).to_numpy(dtype=float)
        ax.plot(xs, mean, lw=1.5, color=palette[0])
        ax.fill_between(xs, mean - band * std, mean + band * std,
                        alpha=0.18, color=palette[0], linewidth=0)
        stats_out["overall"] = {"final_mean": round(float(mean[-1]), 4)}
    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)
    if title:
        ax.set_title(title)
    paths = _save_fig(fig, save_path, save_pdf)
    _save_recipe("line_band", {"x": x, "y": y, "group": group, "band": band}, paths, data=df)
    caption = make_caption("line_band", x=x, y=y, group=group,
                           yerr="std")
    return {"save_path": paths[0], "paths": paths, "final_stats": stats_out, "caption": caption}


def _demo():
    _setup_style()
    samples = SKILL_ROOT / "samples"
    print(f"技能根目录：{SKILL_ROOT}")
    print(f"示例数据目录：{samples}\n")

    df1 = pd.read_csv(samples / "demo_group_comparison.csv")
    r1 = grouped_bar(df1, x="dataset", y="accuracy", group="model", yerr="std",
                     ylabel="测试准确率/(%)",
                     save_path=DEFAULT_OUT / "demo_1_grouped_bar.png")
    print("1) 分组柱状图 →", r1["save_path"])
    print(r1["table"].to_string(index=False), "\n")

    r2 = grouped_box(df1, x="dataset", y="accuracy", group="model",
                     ylabel="测试准确率/(%)",
                     save_path=DEFAULT_OUT / "demo_2_grouped_box.png")
    print("2) 分组箱线图 →", r2["save_path"], "\n")

    df2 = pd.read_csv(samples / "demo_correlation.csv")
    r3 = scatter_fit(df2, x="train_samples", y="accuracy", fit="linear",
                     xlabel="训练样本量", ylabel="测试准确率/(%)",
                     save_path=DEFAULT_OUT / "demo_3_scatter_fit.png")
    print("3) 散点+拟合 →", r3["save_path"])
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r3.items() if k != "save_path"}, "\n")

    df3 = pd.read_csv(samples / "demo_metrics.csv")
    r4 = heatmap(df3.corr(numeric_only=True), title="模型配置-性能指标相关矩阵",
                 save_path=DEFAULT_OUT / "demo_4_heatmap.png")
    print("4) 相关热力图 →", r4["save_path"])

    df4 = pd.read_csv(samples / "demo_training_curve.csv")
    r5 = plot_line(df4, x="epoch", y="val_accuracy", group="model",
                   xlabel="训练轮次/epoch", ylabel="验证准确率/(%)",
                   save_path=DEFAULT_OUT / "demo_5_plot_line.png", save_pdf=True)
    print("5) 训练曲线折线图 →", r5["paths"])
    print("   各模型最优点：", {k: (v["x"], round(v["y"], 2)) for k, v in r5["best"].items()}, "\n")

    df5 = pd.read_csv(samples / "demo_group_comparison.csv")
    sub5 = df5[df5["dataset"] == "CIFAR-10"][["model", "accuracy"]]
    r6 = violin(sub5, x="model", y="accuracy", ylabel="测试准确率/(%)",
                save_path=DEFAULT_OUT / "demo_6_violin.png")
    print("6) 小提琴图 →", r6["save_path"], "｜图注：", r6["caption"])

    r7 = qq_plot(df5, y="accuracy", group="dataset",
                 save_path=DEFAULT_OUT / "demo_7_qq_plot.png")
    print("7) Q-Q图 →", r7["save_path"])
    print("   正态性判定：", {k: v["normal"] for k, v in r7["groups"].items()}, "\n")

    df6 = pd.read_csv(samples / "demo_binary_classification.csv")
    r8 = roc_curves(df6, label_col="y_true", score_col="y_score", model_col="model",
                    title="三种模型的ROC曲线对比",
                    save_path=DEFAULT_OUT / "demo_8_roc_curves.png")
    print("8) ROC曲线 →", r8["save_path"])
    print("   AUC：", {k: v["auc"] for k, v in r8["models"].items()}, "\n")

    r9 = pr_curves(df6, label_col="y_true", score_col="y_score", model_col="model",
                   title="三种模型的PR曲线对比",
                   save_path=DEFAULT_OUT / "demo_9_pr_curves.png")
    print("9) PR曲线 →", r9["save_path"])
    print("   AP：", {k: v["ap"] for k, v in r9["models"].items()}, "\n")

    r10 = confusion_matrix(df6[df6["model"] == "GBDT"], true_col="y_true", pred_col="y_pred",
                           normalize=True, title="GBDT模型混淆矩阵（行归一化）",
                           save_path=DEFAULT_OUT / "demo_10_confusion_matrix.png")
    print("10) 混淆矩阵 →", r10["save_path"])
    print("    总体准确率：", r10["accuracy"], "｜各类F1：", {k: v["f1"] for k, v in r10["per_class"].items()}, "\n")

    df7 = pd.read_csv(samples / "demo_metrics.csv")
    model_agg = (df7.assign(bucket=pd.cut(df7["params_M"], [0, 0.05, 0.1, 0.3, 1],
                                         labels=["tiny", "small", "medium", "large"]))
                 .groupby("bucket", observed=True)
                 .agg(top1=("top1_acc_%", "mean"), flops=("flops_G", "mean"),
                      latency=("latency_ms", "mean"), train=("train_hours", "mean"))
                 .reset_index())
    r11 = radar(model_agg, metrics=["top1", "flops", "latency", "train"], model_col="bucket",
                title="不同参数规模模型的综合性能对比",
                higher_is_better={"latency": False, "train": False},
                save_path=DEFAULT_OUT / "demo_11_radar.png")
    print("11) 雷达图 →", r11["save_path"], "\n")

    df8 = pd.read_csv(samples / "demo_training_multi_seed.csv")
    r12 = line_band(df8, x="epoch", y="val_accuracy", group="model",
                    xlabel="训练轮次/epoch", ylabel="验证准确率/(%)",
                    title="多seed训练稳定性（均值±1倍标准差）",
                    save_path=DEFAULT_OUT / "demo_12_line_band.png")
    print("12) 误差带折线 →", r12["save_path"])
    print("    最终指标：", r12["final_stats"], "｜图注：", r12["caption"])

    print("\n全部演示图输出完毕（演示数据为人工构造，仅用于功能演示）")


def main(argv=None):
    ap = argparse.ArgumentParser(description="学术出图模板脚本")
    ap.add_argument("--demo", action="store_true", help="用 samples/ 示例数据生成十二张演示图")
    ap.add_argument("--out", default=None, help="演示图输出目录（默认 .temp/plots/）")
    args = ap.parse_args(argv)
    if args.out:
        global DEFAULT_OUT
        DEFAULT_OUT = Path(args.out)
    if args.demo:
        _demo()
    else:
        ap.print_help()


if __name__ == "__main__":
    main(sys.argv[1:])
