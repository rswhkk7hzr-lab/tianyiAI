# -*- coding: utf-8 -*-
"""robustness_check.py — 实验结论稳健性检验器（academic-research 技能 · 领域创新工具）

针对研究问题 RQ1：单次运行（单 seed）得出的方法优劣结论可信吗？换一批
随机种子结论会翻转吗？要跑几个 seed 结论才稳？

输入多 seed 实验结果长表（method × seed × metric），输出：

  - 逐 seed 排名翻转分析（bump chart：名次线交叉即结论翻转）
  - 最少稳健 seed 数（子集共识率曲线：k 个 seed 时与全体共识一致的占比）
  - 结论翻转率 + 配对显著性检验（同 seed 配对，消掉种子效应）
  - 稳健性判定卡片（稳健 / 边际 / 脆弱）+ Markdown 报告 + --html

设计原则：与 train_doctor 同源——确定性统计规则、每条结论附数值证据、
判定只出证据与建议，最终解释权归研究者。

用法：
  python robustness_check.py 结果.csv --group model --value acc
  python robustness_check.py 结果.csv --group model --value acc --task 告警工单分类
  python robustness_check.py --demo          # 内置多 seed 样例自验

> AI生成
"""

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import plot_templates as pt  # noqa: E402  复用学术样式与中文字体初始化

DEFAULT_OUT = Path(".temp") / "robustness"

_GROUP_CAND = ["model", "method", "config", "strategy", "group", "name"]
_SEED_CAND = ["seed", "random_seed", "replicate", "rep", "run_id", "fold"]
_TASK_CAND = ["dataset", "task", "benchmark", "corpus"]


def _match_col(df, candidates):
    low = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in low:
            return low[cand]
    return None


def load_results(path, group=None, value=None, seed_col=None, task_col=None, task=None):
    df = pd.read_csv(path)
    g = group or _match_col(df, _GROUP_CAND)
    s = seed_col or _match_col(df, _SEED_CAND)
    v = value
    if v is None:
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != s]
        v = numeric[0] if numeric else None
    t = task_col or _match_col(df, _TASK_CAND)
    if g is None or s is None or v is None:
        raise SystemExit(f"列识别失败：需要方法列/种子列/指标列，当前列={list(df.columns)}")
    if t is not None and task is not None:
        df = df[df[t] == task]
        if df.empty:
            raise SystemExit(f"任务 '{task}' 无数据；可选：{sorted(df[t].unique()) if t else []}")
    return df, g, s, v, t


def analyze(df, g, s, v, min_agree=0.95):
    """核心分析：逐 seed 排名、翻转率、最少稳健 seed 数、配对显著性。"""
    methods = sorted(df[g].unique())
    seeds = sorted(df[s].unique())
    wide = df.pivot_table(index=s, columns=g, values=v, aggfunc="mean")

    # 逐 seed 排名（rank 1 = 最优）
    ranks = wide.rank(axis=1, ascending=False)
    # 全体共识排名（多 seed 均值）
    mean_rank = wide.mean().rank(ascending=False)
    consensus_winner = mean_rank.idxmin()

    # 翻转检测：逐 seed 最优 vs 共识最优
    seed_winners = wide.idxmax(axis=1)
    flips = seed_winners[seed_winners != consensus_winner]
    flip_rate = len(flips) / len(seeds)

    # 前两名逐 seed 序翻转
    top2 = list(mean_rank.nsmallest(2).index)
    if len(top2) == 2:
        a, b = top2
        order_flips = int((wide[a] < wide[b]).sum())
        pair = (a, b, order_flips)
    else:
        pair = None

    # 最少稳健 seed 数：所有 size-k 子集中"最优者与共识一致"的占比
    stability = []
    min_k = None
    for k in range(1, len(seeds) + 1):
        combos = list(itertools.combinations(wide.index, k))
        agree = sum(1 for c in combos if wide.loc[list(c)].mean().idxmax() == consensus_winner)
        rate = agree / len(combos)
        stability.append((k, rate, len(combos)))
        if min_k is None and rate >= min_agree:
            min_k = k

    # 配对显著性（前两名，按 seed 配对）
    sig = {}
    if pair:
        a, b, _ = pair
        try:
            from scipy import stats
            diff = wide[a] - wide[b]
            t_stat, p_t = stats.ttest_rel(wide[a], wide[b])
            sig = {"test": "paired t-test", "statistic": round(float(t_stat), 3),
                   "p": float(p_t), "mean_diff": round(float(diff.mean()), 3)}
            try:
                w_stat, p_w = stats.wilcoxon(wide[a], wide[b])
                sig["wilcoxon_p"] = float(p_w)
            except ValueError:
                pass
        except ImportError:
            sig = {"test": "skipped", "note": "scipy 缺失"}

    # 判定
    if flip_rate == 0 and (not sig or sig.get("p", 1) < 0.05):
        verdict, level = "结论稳健", "低"
    elif flip_rate <= 0.2:
        verdict, level = "结论边际", "中"
    else:
        verdict, level = "结论脆弱", "高"

    return {
        "methods": methods, "seeds": seeds, "wide": wide, "ranks": ranks,
        "mean_rank": mean_rank, "consensus_winner": consensus_winner,
        "seed_winners": seed_winners, "flips": flips, "flip_rate": flip_rate,
        "top2_pair": pair, "stability": stability, "min_k": min_k,
        "sig": sig, "verdict": verdict, "level": level,
    }


def plot_bump(res, out_png):
    """逐 seed 名次 bump chart——名次线交叉=结论翻转。"""
    import matplotlib.pyplot as plt
    ranks, wide, seeds = res["ranks"], res["wide"], res["seeds"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    colors = plt.cm.tab10.colors
    for i, m in enumerate(ranks.columns):
        ax.plot(ranks.index, ranks[m], "o-", color=colors[i % 10],
                lw=2, ms=7, label=m)
    # 翻转 seed 背景标红
    for seed in res["flips"].index:
        ax.axvspan(seed - 0.35, seed + 0.35, color="#e74c3c", alpha=0.08)
    ax.set_yticks(sorted(set(ranks.values.ravel().tolist())))
    ax.set_ylim(len(ranks.columns) + 0.5, 0.5)  # rank1 在上
    ax.set_xticks(seeds)
    ax.set_xlabel("随机种子 seed")
    ax.set_ylabel("名次（1=最优）")
    ax.set_title("逐 seed 名次稳定性——交叉即结论翻转")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    for seed in res["flips"].index:
        ax.annotate("翻转", xy=(seed, 0.55), ha="center", fontsize=8, color="#e74c3c")
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def plot_stability(res, out_png, min_agree):
    """子集共识率曲线——最少需要几个 seed。"""
    import matplotlib.pyplot as plt
    ks = [x[0] for x in res["stability"]]
    rates = [x[1] for x in res["stability"]]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot(ks, [r * 100 for r in rates], "o-", color="#2c6fbb", lw=2, ms=7)
    ax.axhline(min_agree * 100, color="#e67e22", ls="--", lw=1.2,
               label=f"共识阈值 {min_agree:.0%}")
    if res["min_k"]:
        ax.axvline(res["min_k"], color="#27ae60", ls=":", lw=1.4)
        ax.annotate(f"最少 {res['min_k']} seed", xy=(res["min_k"], min_agree * 100),
                    xytext=(res["min_k"] + 0.4, min_agree * 100 - 18),
                    fontsize=9, color="#27ae60",
                    arrowprops=dict(arrowstyle="->", color="#27ae60", lw=0.8))
    ax.set_ylim(0, 105)
    ax.set_xticks(ks)
    ax.set_xlabel("使用的 seed 数量 k")
    ax.set_ylabel("与全体共识一致的占比 (%)")
    ax.set_title("结论稳定性曲线——要几个 seed 才稳？")
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def build_report(res, src, g, v, min_agree, bump_png, stab_png):
    L = []
    L.append("# 实验结论稳健性检验报告")
    L.append("")
    L.append(f"**数据源**：`{src}`　|　方法列 `{g}`　|　指标 `{v}`　|　"
             f"seed 数 {len(res['seeds'])}　|　方法数 {len(res['methods'])}")
    L.append("")
    L.append(f"### [风险等级：{res['level']}] **{res['verdict']}**——"
             f"全体共识最优 **{res['consensus_winner']}**；"
             f"逐 seed 最优翻转率 **{res['flip_rate']:.0%}**"
             f"（{len(res['flips'])}/{len(res['seeds'])} 个 seed 与共识不一致）")
    L.append("")
    L.append("## 逐 seed 最优")
    L.append("")
    L.append("| seed | " + " | ".join(str(x) for x in res["seeds"]) + " |")
    L.append("|" + "---|" * (len(res["seeds"]) + 1))
    winners = [res["seed_winners"][x] for x in res["seeds"]]
    L.append("| 最优 | " + " | ".join(
        (f"**{w}** ⚠翻转" if w != res["consensus_winner"] else w) for w in winners) + " |")
    L.append("")
    L.append("## 多 seed 汇总（均值±std）")
    L.append("")
    L.append("| 方法 | 均值±std | 共识名次 |")
    L.append("|---|---|---|")
    for m in res["mean_rank"].sort_values().index:
        vals = res["wide"][m]
        bold = "**" if m == res["consensus_winner"] else ""
        L.append(f"| {bold}{m}{bold} | {vals.mean():.2f}±{vals.std():.2f} | "
                 f"{int(res['mean_rank'][m])} |")
    L.append("")
    if res["top2_pair"]:
        a, b, of = res["top2_pair"]
        L.append(f"## 冠亚军对决：{a} vs {b}")
        L.append("")
        L.append(f"- 逐 seed 序翻转：{of}/{len(res['seeds'])} 个 seed 中 {b} 反超 {a}")
        sg = res["sig"]
        if sg and sg.get("test") != "skipped":
            L.append(f"- 配对 t 检验（同 seed 配对）：t={sg['statistic']}，p={sg['p']:.4f}，"
                     f"平均差 {sg['mean_diff']:+.2f}"
                     + (f"；Wilcoxon p={sg['wilcoxon_p']:.4f}" if "wilcoxon_p" in sg else ""))
            L.append(f"- 判读：{'差异显著' if sg['p'] < 0.05 else '差异不显著——谨慎宣称优劣'}")
        L.append("")
    L.append("## 最少稳健 seed 数")
    L.append("")
    if res["min_k"]:
        L.append(f"子集共识率达到 {min_agree:.0%} 的最少 seed 数：**{res['min_k']}**"
                 f"（当前用了 {len(res['seeds'])} 个 seed）")
    else:
        L.append(f"即使全部 {len(res['seeds'])} 个 seed 也仅有部分子集与共识一致——"
                 f"**结论对该实验规模而言不稳定，建议增加 seed 或扩大差异**")
    L.append("")
    L.append("| k(seed数) | 与共识一致的子集占比 | 子集数 |")
    L.append("|---|---|---|")
    for k, r, n in res["stability"]:
        L.append(f"| {k} | {r:.0%} | {n} |")
    L.append("")
    L.append("## 建议")
    L.append("")
    if res["level"] == "高":
        L.append("- 结论当前不可信：先按翻转 seed 排查（数据划分/训练是否异常），再增跑 seed")
        L.append("- 论文中严禁只报单 seed 结果，须报 mean±std 与显著性检验")
    elif res["level"] == "中":
        L.append("- 建议补跑到 ≥5 seeds 复检；报告均值±std 与配对显著性")
        L.append("- 若差异本身很小，考虑改用更大的有效数据源而非加 seed")
    else:
        L.append("- 结论在该 seed 集合下稳健；仍建议在论文中如实报告 seed 数与方差")
    L.append("")
    L.append("## 附图")
    L.append("")
    L.append(f"![逐seed名次稳定性]({bump_png.name})")
    L.append(f"![结论稳定性曲线]({stab_png.name})")
    return "\n".join(L) + "\n"


def run(path, group=None, value=None, seed_col=None, task_col=None, task=None,
        min_agree=0.95, outdir=None, html=False):
    out = Path(outdir) if outdir else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    df, g, s, v, t = load_results(path, group, value, seed_col, task_col, task)
    res = analyze(df, g, s, v, min_agree)

    stem = Path(path).stem + (f"_{task}" if task else "")
    bump_png = out / f"{stem}_bump.png"
    stab_png = out / f"{stem}_stability.png"
    plot_bump(res, bump_png)
    plot_stability(res, stab_png, min_agree)

    fingerprint = hashlib.md5(
        pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:12]
    payload = {
        "source": str(path), "group_col": g, "seed_col": s, "value_col": v,
        "task": task, "fingerprint": fingerprint,
        "consensus_winner": res["consensus_winner"],
        "flip_rate": res["flip_rate"], "flipped_seeds": [int(x) for x in res["flips"].index],
        "min_stable_seeds": res["min_k"], "verdict": res["verdict"],
        "level": res["level"], "significance": res["sig"],
    }
    (out / f"{stem}.robustness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = build_report(res, Path(path).name, g, v, min_agree, bump_png, stab_png)
    md_path = out / f"{stem}_report.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"[✓] 判定：{res['verdict']}（{res['level']}险）　翻转率 {res['flip_rate']:.0%}　"
          f"共识最优 {res['consensus_winner']}　最少seed数 {res['min_k']}")
    print(f"[✓] 报告 {md_path}　|　图 {bump_png.name}/{stab_png.name}　|　指纹 {fingerprint}")
    if html:
        from report_html import render_file
        hp = render_file(md_path, out / f"{stem}_report.html")
        print(f"[✓] HTML {hp}")
    return md_path


def _demo():
    src = SKILL_ROOT / "samples" / "demo_group_comparison.csv"
    if not src.exists():
        raise SystemExit("samples/demo_group_comparison.csv 不存在")
    df = pd.read_csv(src)
    tcol = _match_col(df, _TASK_CAND)
    tasks = df[tcol].unique().tolist() if tcol else [None]
    for tk in tasks[:2]:  # 演示两个任务：一个有翻转、一个无翻转
        print(f"\n=== 任务：{tk} ===" if tk else "")
        run(src, task=tk, html=True)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="实验结论稳健性检验器")
    ap.add_argument("csv", nargs="?", help="多seed结果CSV（长表：方法×seed×指标）")
    ap.add_argument("--group", help="方法列名（默认自动识别 model/method/...）")
    ap.add_argument("--value", help="指标列名（默认第一个数值列）")
    ap.add_argument("--seed-col", help="seed列名（默认自动识别）")
    ap.add_argument("--task-col", help="任务列名（默认自动识别 dataset/task）")
    ap.add_argument("--task", help="只分析指定任务（默认全表合并）")
    ap.add_argument("--min-agree", type=float, default=0.95, help="共识阈值，默认0.95")
    ap.add_argument("--outdir", help="输出目录（默认 .temp/robustness）")
    ap.add_argument("--html", action="store_true", help="追加单文件HTML报告")
    ap.add_argument("--demo", action="store_true", help="内置样例自验")
    a = ap.parse_args()
    if a.demo:
        _demo()
    elif a.csv:
        run(a.csv, a.group, a.value, a.seed_col, a.task_col, a.task,
            a.min_agree, a.outdir, a.html)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
