# -*- coding: utf-8 -*-
"""pathology_correlate.py — 训练病理 × 泛化性能相关性分析器（academic-research 技能 · 领域创新工具）

针对研究问题 RQ2：训练病理模式（过拟合/spike/振荡/发散……）与最终泛化
性能是否存在相关性？能否用训练曲线症状提前预测实验成败？

工作原理（工具输出即研究数据）：

  1. 对每个 run 的训练日志调用 train_doctor 规则引擎 → 诊断标签
     （病理类型 code + 严重等级 severity）
  2. 与结果表（run → final 指标）按 run 名合并
  3. 分组统计：各病理组的最终性能 均值±std；健康组 vs 病理组差异检验；
     "含病理"二值标记与性能的关联强度（点二列相关效应量 r）
  4. 产出：分组对比图 + 相关性报告（风险卡片格式）+ .correlation.json + --html

这是"用诊断工具做方法学研究"的闭环：诊断器的输出不是终点，而是自变量。

用法：
  python pathology_correlate.py --logs 多run日志.csv --results 结果.csv
  python pathology_correlate.py --logs 日志.csv --results 结果.csv --value final_acc --html
  python pathology_correlate.py --demo

> AI生成
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import plot_templates as pt  # noqa: E402
import train_doctor as td  # noqa: E402

DEFAULT_OUT = Path(".temp") / "pathology_corr"

_SEV_RANK = {"高": 3, "中": 2, "低": 1, "提示": 0}
_CODE_CN = {"divergence": "训练发散", "loss_spike": "Loss spike", "overfit": "过拟合",
            "underfit": "欠拟合", "not_converged": "未收敛", "oscillation": "振荡偏大",
            "early_stop": "早停建议", "eval_lt_train": "eval倒置",
            "metric_loss_diverge": "指标背离", "lr_schedule": "调度建议",
            "healthy": "健康"}


def collect_diagnoses(logs_path):
    """对每个 run 执行 train_doctor 诊断，返回 {run: {codes, max_sev, n_findings}}。"""
    df = pd.read_csv(logs_path)
    run_col = td.detect_columns(df)["run"]
    out = {}
    if run_col is None:
        diag = td.diagnose(df)
        out[Path(logs_path).stem] = _summ(diag)
    else:
        for name, sub in df.groupby(run_col):
            out[str(name)] = _summ(td.diagnose(sub))
    return out


def _summ(diag):
    fs = diag["findings"]
    return {
        "codes": [f["code"] for f in fs],
        "primary": fs[0]["code"] if fs else "healthy",
        "max_sev": max((_SEV_RANK.get(f["severity"], 0) for f in fs), default=0),
        "n_findings": len(fs),
        "has_pathology": any(_SEV_RANK.get(f["severity"], 0) >= 2 for f in fs),
    }


def merge_results(diags, results_path, value=None, run_col=None):
    res = pd.read_csv(results_path)
    rc = run_col or next((c for c in res.columns if c.lower() in ("run", "name", "id", "exp")), None)
    if rc is None:
        raise SystemExit(f"结果表缺少 run 列，现有列：{list(res.columns)}")
    v = value or next((c for c in res.columns
                       if pd.api.types.is_numeric_dtype(res[c]) and c != rc), None)
    if v is None:
        raise SystemExit(f"结果表缺少数值指标列：{list(res.columns)}")
    rows = []
    for _, r in res.iterrows():
        name = str(r[rc])
        if name not in diags:
            continue
        d = diags[name]
        rows.append({"run": name, "value": r[v], "primary": d["primary"],
                     "max_sev": d["max_sev"], "n_findings": d["n_findings"],
                     "has_pathology": d["has_pathology"], "codes": d["codes"]})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("诊断 run 与结果表 run 名无交集——检查两边命名是否一致")
    return df, v


def correlate(df, value_name):
    """健康 vs 病理 分组统计 + 检验 + 效应量。"""
    healthy = df[~df["has_pathology"]]["value"]
    sick = df[df["has_pathology"]]["value"]
    stats = {"n_healthy": len(healthy), "n_sick": len(sick)}
    if len(sick) and len(healthy):
        stats["healthy_mean"] = float(healthy.mean())
        stats["sick_mean"] = float(sick.mean())
        stats["diff"] = float(healthy.mean() - sick.mean())
        # 点二列相关效应量（二值×连续）
        xs = df["has_pathology"].astype(int).values
        ys = df["value"].values
        if xs.std() > 0 and ys.std() > 0:
            stats["r_pb"] = float(np.corrcoef(xs, ys)[0, 1])
        try:
            from scipy import stats as sst
            t, p = sst.ttest_ind(healthy, sick, equal_var=False)
            stats["test"], stats["t"], stats["p"] = "Welch t", float(t), float(p)
            rho, pr = sst.spearmanr(df["has_pathology"].astype(int), df["value"])
            stats["rho"], stats["rho_p"] = float(rho), float(pr)
            if len(df) >= 8:
                u, pu = sst.mannwhitneyu(healthy, sick, alternative="two-sided")
                stats["mw_p"] = float(pu)
        except ImportError:
            stats["test"] = "skipped(scipy缺失)"
    # 按主要病理分组
    grp = df.assign(group=df["primary"].map(lambda c: _CODE_CN.get(c, c))).groupby("group")["value"]
    stats["groups"] = [{"group": g, "n": int(s.size),
                        "mean": float(s.mean()), "std": float(s.std())}
                       for g, s in grp]
    return stats


def plot_corr(df, stats, value_name, out_png):
    import matplotlib.pyplot as plt
    groups = stats["groups"]
    order = sorted(groups, key=lambda g: -g["mean"])
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    labels, means, stds, ns, cols = [], [], [], [], []
    for g in order:
        labels.append(f"{g['group']}\n(n={g['n']})")
        means.append(g["mean"]); stds.append(g["std"]); ns.append(g["n"])
        cols.append("#27ae60" if g["group"] == "healthy" or g["group"] == "健康" else "#c0392b"
                    if g["mean"] < stats.get("healthy_mean", 1e9) - abs(stats.get("diff", 0)) / 2
                    else "#e67e22")
    xs = np.arange(len(labels))
    ax.bar(xs, means, yerr=stds, capsize=4, color=cols, alpha=0.85, width=0.62)
    # 叠加散点
    cmap = {g["group"]: i for i, g in enumerate(order)}
    for _, r in df.iterrows():
        gname = _CODE_CN.get(r["primary"], r["primary"])
        ax.scatter(cmap[gname] + np.random.uniform(-0.18, 0.18), r["value"],
                   s=16, color="#2c3e50", alpha=0.55, zorder=3)
    ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel(value_name)
    ax.set_title("训练病理分组 × 最终性能——绿=健康组")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def verdict_of(stats):
    """显著性取参数/非参数检验的较优证据（小样本+离群下非参数更可靠）。"""
    if stats.get("test") in (None, "skipped(scipy缺失)"):
        return "样本不足，无法判定相关性", "提示"
    ps = [v for k, v in stats.items() if k in ("p", "mw_p", "rho_p") and v is not None]
    if not ps:
        return "样本不足，无法判定相关性", "提示"
    p_min, r = min(ps), abs(stats.get("rho", stats.get("r_pb", 0)))
    if p_min < 0.05 and r >= 0.4:
        return "病理与泛化性能显著相关（中强关联）——训练症状可作早期预警", "低"
    if p_min < 0.05:
        return "病理与性能显著相关但效应较弱", "低"
    if r >= 0.4:
        return "效应量可观但未达显著——建议扩充 run 数", "中"
    return "未检出显著相关性（当前样本下症状对性能预测力有限）", "中"


def run(logs, results, value=None, run_col=None, outdir=None, html=False):
    out = Path(outdir) if outdir else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    diags = collect_diagnoses(logs)
    df, v = merge_results(diags, results, value, run_col)
    stats = correlate(df, v)
    verdict, level = verdict_of(stats)

    stem = f"{Path(logs).stem}_corr"
    png = out / f"{stem}_groups.png"
    plot_corr(df, stats, v, png)

    L = ["# 训练病理 × 泛化性能 相关性报告", ""]
    L.append(f"**数据源**：日志 `{Path(logs).name}` + 结果 `{Path(results).name}`　|　"
             f"run 数 {len(df)}　|　指标 `{v}`　|　诊断引擎 train_doctor 规则引擎")
    L.append("")
    L.append(f"### [风险等级：{level}] **{verdict}**")
    L.append("")
    L.append("## 分组统计")
    L.append("")
    L.append("| 病理分组 | n | 均值±std |")
    L.append("|---|---|---|")
    for g in sorted(stats["groups"], key=lambda x: -x["mean"]):
        L.append(f"| {g['group']} | {g['n']} | {g['mean']:.2f}±{g['std']:.2f} |")
    L.append("")
    L.append("## 健康组 vs 病理组")
    L.append("")
    if "diff" in stats:
        L.append(f"- 健康组(n={stats['n_healthy']}) 均值 {stats['healthy_mean']:.2f}　"
                 f"病理组(n={stats['n_sick']}) 均值 {stats['sick_mean']:.2f}　"
                 f"差值 {stats['diff']:+.2f}")
        L.append(f"- Spearman 秩相关 ρ={stats.get('rho', float('nan')):.3f}"
                 f"（p={stats.get('rho_p', float('nan')):.4f}，|ρ|≥0.4 视为中强关联）")
        L.append(f"- {stats['test']} 检验：p={stats.get('p', float('nan')):.4f}"
                 + (f"；Mann-Whitney p={stats['mw_p']:.4f}" if "mw_p" in stats else ""))
        p_min = min(v for k, v in stats.items() if k in ("p", "mw_p", "rho_p"))
        L.append(f"- 判读：{'差异显著' if p_min < 0.05 else '差异不显著'}"
                 "（小样本+离群点场景以非参数检验为准）")
    else:
        L.append("样本不足（健康组或病理组为空），无法做组间检验。")
    L.append("")
    L.append("## 研究意义")
    L.append("")
    L.append("若相关性成立：train_doctor 诊断可在训练中期提前预警实验成败，"
             "省掉无效 run 的评估成本——这是'训练监控→实验决策'闭环的证据链。")
    L.append("若未达显著：可能样本不足或病理被及时干预未传导至结果，如实报告阴性结果同样有方法学价值。")
    L.append("")
    L.append("## 附图")
    L.append("")
    L.append(f"![病理分组×最终性能]({png.name})")

    md = out / f"{stem}_report.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    fp = hashlib.md5(pd.util.hash_pandas_object(
        df.assign(codes=df["codes"].astype(str)), index=True).values.tobytes()).hexdigest()[:12]
    payload = {"logs": str(logs), "results": str(results), "value": v,
               "n_runs": len(df), "fingerprint": fp, "verdict": verdict,
               "level": level, "stats": stats}
    (out / f"{stem}.correlation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"[✓] {verdict}（{level}）　run={len(df)}　"
          f"rho={stats.get('rho', float('nan')):.3f}　"
          f"MW_p={stats.get('mw_p', stats.get('p', float('nan'))):.4f}")
    print(f"[✓] 报告 {md}　|　图 {png.name}")
    if html:
        from report_html import render_file
        print(f"[✓] HTML {render_file(md, out / f'{stem}_report.html')}")
    return md


def _demo():
    s = SKILL_ROOT / "samples"
    run(s / "demo_trainlog_multi_run.csv", s / "demo_run_results.csv",
        value="final_acc", html=True)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="训练病理×泛化性能相关性分析器")
    ap.add_argument("--logs", help="训练日志CSV（多run含run列或单run）")
    ap.add_argument("--results", help="run结果CSV（run+数值指标列）")
    ap.add_argument("--value", help="指标列名（默认第一个数值列）")
    ap.add_argument("--run-col", help="结果表run列名")
    ap.add_argument("--outdir")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        _demo()
    elif a.logs and a.results:
        run(a.logs, a.results, a.value, a.run_col, a.outdir, a.html)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
