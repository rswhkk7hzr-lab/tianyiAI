# -*- coding: utf-8 -*-
"""train_doctor.py — 大模型微调训练曲线诊断器（academic-research 技能 v3.0 · 领域核心工具）

输入微调训练日志 CSV（epoch/step + train_loss/eval_loss/指标/lr），按确定性
规则引擎自动检出常见训练病理并给出处置建议：

  - 训练发散（loss 爆炸 / NaN）
  - Loss spike（疑似梯度爆炸，单点突跳）
  - 过拟合（eval 指标拐点后持续恶化而 train 继续改善）
  - 欠拟合 / 未充分收敛（末段仍快速下降或双侧高位平台）
  - 训练振荡过大（疑似学习率偏高）
  - 早停建议（最佳 eval 点显著早于训练终点）
  - eval < train 持续倒置（正则不对称 / 数据泄漏提示）
  - eval_loss 与评估指标走势背离（评估协议提示）
  - 恒定学习率 + 后期平台（调度建议）

输出三件套：Markdown 诊断报告（风险等级卡片，report_html 兼容）+
标注诊断图（问题区域阴影 / spike 标记 / 早停竖线）+ .diagnosis.json
（结构化结论与数据指纹，可复现核对）。

设计原则：
  1. 确定性规则而非"感觉"——每条结论附 epoch 区间与数值证据，可复核；
  2. 宁可多提示不漏报——边界情况降级为"提示"，判断权留给研究者；
  3. 默认即满意初版——零参数自动识别列名，一行参数可覆盖。

用法：
  python train_doctor.py 训练日志.csv                 # 自动识别列，输出诊断三件套
  python train_doctor.py 日志.csv --html              # 追加单文件 HTML 报告
  python train_doctor.py 日志.csv --train-loss loss --eval-loss dev_loss
  python train_doctor.py --demo                       # 四种典型病理样例全量自验

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

import plot_templates as pt  # noqa: E402  复用学术样式与中文字体初始化

DEFAULT_OUT = Path(".temp") / "train_doctor"

# ---------------------------------------------------------------------------
# 列名自动识别（覆盖常见训练框架/日志导出习惯）
# ---------------------------------------------------------------------------

_STEP_CAND = ["epoch", "step", "iteration", "iter", "global_step", "round"]
_TRAIN_LOSS_CAND = ["train_loss", "training_loss", "loss", "train-loss"]
_EVAL_LOSS_CAND = ["eval_loss", "val_loss", "valid_loss", "validation_loss",
                   "dev_loss", "test_loss", "eval-loss", "val-loss"]
_LR_CAND = ["learning_rate", "lr", "lr_rate"]
_RUN_CAND = ["run", "model", "config", "name", "exp", "experiment", "trial"]
# 指标列：含这些关键词的数值列视为评估指标（loss/lr/step 已排除在外）
_METRIC_KEYS = ("acc", "f1", "bleu", "rouge", "score", "auc", "prec",
                "recall", "map", "top", "exact", "em", "wer", "ppl",
                "perplexity", "eval_")
# 越小越好的指标（其余默认越大越好）
_LOWER_BETTER = ("loss", "err", "wer", "ppl", "perplexity", "latency")


def _match_col(df, candidates):
    low = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in low:
            return low[cand]
    return None


def detect_columns(df):
    """自动识别训练日志列结构，返回 dict；识别不出的字段为 None。"""
    used = set()
    out = {}
    for key, cands in (("step", _STEP_CAND), ("train_loss", _TRAIN_LOSS_CAND),
                       ("eval_loss", _EVAL_LOSS_CAND), ("lr", _LR_CAND),
                       ("run", _RUN_CAND)):
        col = _match_col(df, cands)
        out[key] = col
        if col:
            used.add(col)
    # 指标列 = 数值列 且 命中指标关键词 且 未被占用
    metrics = []
    for c in df.columns:
        if c in used or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        lc = c.lower()
        if any(k in lc for k in _METRIC_KEYS):
            metrics.append(c)
    out["metrics"] = metrics
    # 无 step 列时取首个单调递增数值列，再退化为行号
    if out["step"] is None:
        for c in df.columns:
            if c in used or not pd.api.types.is_numeric_dtype(df[c]):
                continue
            if df[c].is_monotonic_increasing:
                out["step"] = c
                break
    return out


def _metric_higher_better(name):
    lc = name.lower()
    return not any(k in lc for k in _LOWER_BETTER)


# ---------------------------------------------------------------------------
# 规则引擎：每条规则返回 finding dict 或 None
# finding = {code, severity(高/中/低/提示), title, evidence, suggestion,
#            span=(x1,x2) 阴影区间, points=[x,...] 标记点, vline=x 竖线}
# ---------------------------------------------------------------------------

def _ema(s, frac=0.12):
    """指数滑动平均（平滑程度随序列长度自适应）。"""
    span = max(3, int(round(len(s) * frac)))
    return s.ewm(span=span, adjust=False).mean()


def _finite(s):
    return s.replace([np.inf, -np.inf], np.nan)


def _rule_divergence(x, train):
    """训练发散：NaN/Inf 或 loss 升至初始值 10 倍以上。"""
    s = _finite(train)
    if s.isna().any():
        idx = int(s.isna().idxmax())
        return {"code": "divergence", "severity": "高",
                "title": "训练发散：loss 出现 NaN/Inf",
                "evidence": f"第 {x.iloc[idx]} 步起 loss 为非有限值（NaN/Inf），训练已崩溃",
                "suggestion": "立即排查：学习率过大（先降一个数量级）、梯度裁剪缺失（加 clip_norm=1.0）、"
                              "数据含异常样本（检查该步附近 batch）、混合精度溢出（换 bf16 或加 loss scale）",
                "points": [float(x.iloc[idx])]}
    base = float(s.iloc[: max(3, len(s) // 10)].median())
    blowup = s > max(base * 10, base + 10)
    if blowup.any():
        idx = int(blowup.idxmax())
        return {"code": "divergence", "severity": "高",
                "title": "训练发散：loss 爆炸式增长",
                "evidence": f"第 {x.iloc[idx]} 步 train_loss={s.iloc[idx]:.3g}，已达初始水平 "
                            f"{base:.3g} 的 10 倍以上",
                "suggestion": "按发散处置：降低学习率、开启梯度裁剪、检查该步附近数据与优化器状态",
                "points": [float(x.iloc[idx])]}
    return None


def _rule_spikes(x, train):
    """Loss spike：当前点相对"前窗滞后中位数"的突跳（不含未来信息），
    跳变幅度 >4 倍全局稳健尺度 且 相对邻域水平 >15%。"""
    s = _finite(train)
    if len(s) < 15:
        return None
    win = max(5, len(s) // 12) | 1
    med = s.rolling(win, min_periods=win).median().shift(1)  # 滞后中位数
    # 只判定"向上突跳"（逆趋势变差）：下降沿快速下降是良性，不算 spike；
    # 尺度用带符号残差的 MAD 估计（含下降沿，避免正侧 clip 后尺度塌缩为 0）
    resid = s - med
    scale = float(resid.abs().median() * 1.4826) + 1e-9
    jump = resid.clip(lower=0)
    amp = jump / (med.abs() + 1e-9)
    mask = (jump > 4 * scale) & (amp > 0.15) & med.notna()
    idxs = list(np.where(mask)[0])
    if not idxs:
        return None
    # 合并相邻点为一簇，取簇内 z 最大者代表
    clusters, cur = [], [idxs[0]]
    for i in idxs[1:]:
        if i - cur[-1] <= win:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    reps = [max(c, key=lambda i: jump.iloc[i]) for c in clusters]
    pts = [float(x.iloc[i]) for i in reps]
    worst = reps[int(np.argmax([jump.iloc[i] for i in reps]))]
    sev = "高" if len(reps) >= 3 else "中"
    return {"code": "loss_spike", "severity": sev,
            "title": f"Loss spike ×{len(reps)}（疑似梯度爆炸/数据异常）",
            "evidence": f"最显著突跳位于第 {x.iloc[worst]} 步：train_loss={s.iloc[worst]:.3g}，"
                        f"相对前窗中位数 {med.iloc[worst]:.3g} 突升 {amp.iloc[worst]*100:.0f}%"
                        f"（跳变 {jump.iloc[worst]:.3g} = {jump.iloc[worst]/scale:.0f}×稳健尺度）",
            "suggestion": "先区分偶发与反复：偶发 spike 多为脏 batch，可容忍；反复出现应："
                          "①开启/收紧梯度裁剪 ②降低学习率或加 warmup ③核查 spike 步附近数据"
                          "（长度异常/特殊字符/标注错误）④微调场景确认 bf16 精度配置",
            "points": pts}


def _rule_overfit(x, train_loss, eval_loss, eval_metric, metric_name, higher):
    """过拟合：eval 拐点后持续恶化，同时 train 侧仍在改善。"""
    if eval_loss is not None:
        raw = _finite(eval_loss).ffill()
        s = _ema(raw)  # 先平滑再找拐点，避免噪声假拐点
        e_i = int(s.idxmin())
        # 噪声尺度（稳健）：原始-平滑残差的 MAD，用于判定回升是否超越噪声
        noise = float((raw - s).abs().median() * 1.4826) + 1e-9
        rise = (float(s.iloc[-1]) - float(s.iloc[e_i])) / (abs(float(s.iloc[e_i])) + 1e-9)
        rise_abs = float(s.iloc[-1]) - float(s.iloc[e_i])
        n_after = len(s) - e_i - 1
        if n_after >= max(4, len(s) // 8) and rise > 0.08 and rise_abs > 2 * noise:
            tr = _finite(train_loss).ffill()
            tr_sm = _ema(tr)
            train_improved = float(tr_sm.iloc[e_i]) - float(tr_sm.iloc[-1]) > 0
            gap0 = float(s.iloc[e_i] - tr_sm.iloc[e_i])
            gap1 = float(s.iloc[-1] - tr_sm.iloc[-1])
            sev = "高" if rise > 0.25 else "中"
            return {"code": "overfit", "severity": sev,
                    "title": f"过拟合：eval_loss 自第 {x.iloc[e_i]} 步拐点后回升 {rise*100:.0f}%",
                    "evidence": f"eval_loss（平滑）最低点 {float(s.iloc[e_i]):.4g}@第{x.iloc[e_i]}步 → "
                                f"末值 {float(s.iloc[-1]):.4g}；train/eval 差距由 {gap0:.3g} 拉大到 "
                                f"{gap1:.3g}" + ("，且 train_loss 仍在下降" if train_improved else ""),
                    "suggestion": f"最佳 checkpoint 约为第 {x.iloc[e_i]} 步，按此早停；根治方向："
                                  "增训数据/数据增强、提高 dropout 或 weight decay、缩小 LoRA 秩或换更轻基座、"
                                  "降低学习率缩短训练",
                    "span": (float(x.iloc[e_i]), float(x.iloc[-1])),
                    "vline": float(x.iloc[e_i])}
        return None
    if eval_metric is not None:
        s = _finite(eval_metric).ffill()
        e_i = int(s.idxmax()) if higher else int(s.idxmin())
        best = float(s.iloc[e_i])
        last = float(s.iloc[-1])
        drop = (best - last) if higher else (last - best)
        n_after = len(s) - e_i - 1
        if n_after >= max(4, len(s) // 8) and drop > max(0.5, abs(best) * 0.01):
            sev = "高" if drop > max(2.0, abs(best) * 0.05) else "中"
            unit = "个百分点" if abs(best) > 3 else ""
            return {"code": "overfit", "severity": sev,
                    "title": f"过拟合迹象：{metric_name} 自第 {x.iloc[e_i]} 步后回落 {drop:.2f}{unit}",
                    "evidence": f"{metric_name} 最佳 {best:.3g}@第{x.iloc[e_i]}步 → 末值 {last:.3g}",
                    "suggestion": f"最佳 checkpoint 约为第 {x.iloc[e_i]} 步；建议早停并加强正则化",
                    "span": (float(x.iloc[e_i]), float(x.iloc[-1])),
                    "vline": float(x.iloc[e_i])}
    return None


def _rule_underfit(x, train, metric, metric_name, higher):
    """欠拟合/未收敛：末段 train_loss 仍快速下降，或双侧高位平台。"""
    s = _finite(train).ffill()
    n = len(s)
    if n < 10:
        return None
    tail = s.iloc[int(n * 0.9):]
    slope = np.polyfit(np.arange(len(tail)), tail.values, 1)[0]
    rel_drop = -slope * (n * 0.1) / (abs(float(tail.mean())) + 1e-9)
    if rel_drop > 0.10:
        return {"code": "not_converged", "severity": "中",
                "title": "未充分收敛：末段 train_loss 仍在快速下降",
                "evidence": f"最后 10% 步数内 train_loss 相对降幅仍达 {rel_drop*100:.0f}%"
                            f"（{float(tail.iloc[0]):.4g}→{float(tail.iloc[-1]):.4g}）",
                "suggestion": "训练提前终止：增加 epoch、或提高学习率让末段收敛；"
                              "微调场景确认 epoch 设置（常见 3-10）与 lr 是否过小",
                "span": (float(x.iloc[int(n * 0.9)]), float(x.iloc[-1]))}
    # 高位平台：平滑后末 1/3 斜率近零且损失停留在初始区间的上半部
    sm = _ema(s)
    rng = float(sm.max() - sm.min()) + 1e-9
    flat = abs(float(sm.iloc[-1] - sm.iloc[-max(3, n // 6)])) < 0.02 * rng
    high = float(sm.iloc[-1]) > float(sm.min()) + 0.6 * rng
    if flat and high:
        msg = "train_loss 后期平台且处于高位"
        if metric is not None:
            m = _finite(metric).ffill()
            perf = float(m.iloc[-1])
            msg += f"；{metric_name} 末值 {perf:.3g} 亦未见起色"
        return {"code": "underfit", "severity": "中",
                "title": "疑似欠拟合：损失高位平台",
                "evidence": msg,
                "suggestion": "模型容量或训练强度不足：提高学习率、增加 epoch、增大 LoRA 秩/"
                              "换全参微调、检查数据标注质量与任务难度",
                "span": (float(x.iloc[int(n * 0.66)]), float(x.iloc[-1]))}
    return None


def _rule_oscillation(x, train, lr):
    """训练振荡：去趋势残差相对单步趋势降幅过大，且非 spike 型。"""
    s = _finite(train).ffill()
    n = len(s)
    if n < 20:
        return None
    sm = _ema(s)
    # 振荡用一阶差分抖动（MAD of diff）衡量：spike 只占个别差分点，中位数免疫；
    # 初始陡降段也只影响少数差分点，不会像 EMA 残差那样拖尾污染
    d = s.diff()
    jitter = float((d - d.median()).abs().median() * 1.4826)
    total_drop = float(sm.iloc[0] - sm.iloc[-1])
    if jitter <= 1e-9:
        return None
    r = jitter / total_drop if total_drop > 0 else np.inf
    if 0.08 < r <= 0.30 or (total_drop > 0 and r > 0.30):
        sev = "高" if r > 0.30 else "中"
        lr_msg = ""
        if lr is not None and float(pd.Series(lr).nunique()) == 1:
            lr_msg = f"；当前学习率恒定为 {float(pd.Series(lr).iloc[0]):.3g}，可优先尝试下调"
        title = ("振荡淹没净降幅：训练几乎无效（高危）" if sev == "高"
                 else "训练振荡偏大（疑似学习率偏高或 batch 过小）")
        return {"code": "oscillation", "severity": sev,
                "title": title,
                "evidence": f"一阶差分稳健抖动 {jitter:.3g}，为全程净降幅 {total_drop:.3g} "
                            f"的 {r:.0%}{lr_msg}",
                "suggestion": "降低学习率（5-10×）、增大 batch 或梯度累积、加 warmup、"
                              "微调场景优先考虑更保守的 lr 区间（如 1e-5~5e-5）",
                "span": (float(x.iloc[0]), float(x.iloc[-1]))}
    return None


def _rule_early_stop(x, eval_loss, eval_metric, metric_name, higher):
    """早停建议：最佳 eval 点显著早于终点（未被过拟合规则覆盖时给出）。"""
    n = len(x)
    if eval_loss is not None:
        s = _finite(eval_loss).ffill()
        e_i = int(s.idxmin())
        if e_i < 0.7 * (n - 1) and float(s.iloc[-1]) - float(s.iloc[e_i]) < 0.08 * abs(float(s.iloc[e_i])) + 1e-9:
            return {"code": "early_stop", "severity": "低",
                    "title": f"可考虑早停：eval_loss 最佳点在第 {x.iloc[e_i]} 步",
                    "evidence": f"训练继续到第 {x.iloc[-1]} 步，eval_loss 仅变化 "
                                f"{(float(s.iloc[-1])-float(s.iloc[e_i])):.4g}，后段收益极小",
                    "suggestion": f"设置 early_stopping（patience≈{max(3,(n-1-e_i)//2)} 步）可节省约 "
                                  f"{(1-e_i/(n-1))*100:.0f}% 训练时间",
                    "vline": float(x.iloc[e_i])}
    elif eval_metric is not None:
        s = _finite(eval_metric).ffill()
        e_i = int(s.idxmax()) if higher else int(s.idxmin())
        if e_i < 0.7 * (n - 1):
            return {"code": "early_stop", "severity": "低",
                    "title": f"可考虑早停：{metric_name} 最佳点在第 {x.iloc[e_i]} 步",
                    "evidence": f"后 {(n-1-e_i)} 步未再刷新最佳值 {float(s.iloc[e_i]):.3g}",
                    "suggestion": "设置 early_stopping 回传最佳 checkpoint，避免无效训练",
                    "vline": float(x.iloc[e_i])}
    return None


def _rule_eval_lt_train(x, train, eval_loss):
    """eval_loss 持续低于 train_loss：正则不对称或数据泄漏提示。"""
    if eval_loss is None:
        return None
    n = len(x)
    half = slice(int(n * 0.5), n)
    tr_m = float(_finite(train).iloc[half].median())
    ev_m = float(_finite(eval_loss).iloc[half].median())
    if ev_m < tr_m * 0.9:
        return {"code": "eval_lt_train", "severity": "低",
                "title": "eval_loss 持续低于 train_loss（需解释的反常）",
                "evidence": f"后半程中位数：eval_loss={ev_m:.4g} < train_loss={tr_m:.4g}",
                "suggestion": "常见良性原因：训练期 dropout/augmentation 使 train_loss 偏高、"
                              "eval 集更简单、train_loss 为滑动平均口径；"
                              "需排除：eval 集泄漏进训练数据——做一次打乱抽样人工核查"}
    return None


def _rule_metric_loss_diverge(x, eval_loss, metric, metric_name, higher):
    """eval_loss 与评估指标末 1/3 走势背离。"""
    if eval_loss is None or metric is None:
        return None
    n = len(x)
    t = slice(int(n * 0.66), n)
    el = _finite(eval_loss).iloc[t]
    m = _finite(metric).iloc[t]
    if len(el) < 5:
        return None
    el_slope = np.polyfit(np.arange(len(el)), el.values, 1)[0]
    m_slope = np.polyfit(np.arange(len(m)), m.values, 1)[0]
    el_norm = el_slope / (el.abs().mean() + 1e-9)
    m_norm = m_slope / (m.abs().mean() + 1e-9)
    diverge = (el_norm < -0.02 and m_norm < -0.02 * (1 if higher else -1)) or \
              (higher and el_norm < -0.02 and m_norm < 0) or \
              (not higher and el_norm < -0.02 and m_norm > 0)
    if diverge:
        return {"code": "metric_loss_diverge", "severity": "低",
                "title": f"eval_loss 与 {metric_name} 走势背离",
                "evidence": f"末 1/3 段 eval_loss 仍在改善而 {metric_name} 未同步"
                            f"（归一化斜率 {el_norm:.3f} vs {m_norm:.3f}）",
                "suggestion": "排查评估协议：指标口径是否与任务目标一致、eval 集是否同分布、"
                              "阈值是否需校准；loss 改善不等于业务指标改善"}
    return None


def _rule_constant_lr(x, lr, train):
    """恒定学习率 + 后期平台：调度建议（提示级）。"""
    if lr is None or len(x) < 20:
        return None
    lr_s = pd.Series(lr).reset_index(drop=True)
    if lr_s.nunique() > 1:
        return None
    sm = _ema(_finite(train).ffill())
    rng = float(sm.max() - sm.min()) + 1e-9
    tail_flat = abs(float(sm.iloc[-1] - sm.iloc[-max(3, len(sm) // 5)])) < 0.05 * rng
    if tail_flat:
        return {"code": "lr_schedule", "severity": "提示",
                "title": "学习率全程恒定且后期进入平台",
                "evidence": f"lr 恒定 {float(lr_s.iloc[0]):.3g}，末段 loss 变化 <5% 全程幅度",
                "suggestion": "可采用 cosine/linear 衰减或 step decay：末段降 lr 常能再压出一段下降；"
                              "微调常用 cosine + warmup_ratio=0.03-0.1"}
    return None


# ---------------------------------------------------------------------------
# 诊断主流程
# ---------------------------------------------------------------------------

def diagnose(df, *, epoch_col=None, train_loss_col=None, eval_loss_col=None,
             lr_col=None, run_col=None, metric_cols=None):
    """对单条训练日志 DataFrame 执行全部规则，返回诊断 dict。"""
    cols = detect_columns(df)
    epoch_col = epoch_col or cols["step"]
    train_loss_col = train_loss_col or cols["train_loss"]
    eval_loss_col = eval_loss_col or cols["eval_loss"]
    lr_col = lr_col or cols["lr"]
    run_col = run_col or cols["run"]
    metrics = metric_cols or cols["metrics"]

    if train_loss_col is None:
        raise SystemExit("[列识别失败] 未找到 train_loss/loss 列；"
                         "请用 --train-loss 显式指定。现有列：" + ", ".join(df.columns))

    df = df.reset_index(drop=True)
    if epoch_col is not None:
        x = pd.to_numeric(df[epoch_col], errors="coerce").ffill().fillna(0)
    else:
        x = pd.Series(np.arange(len(df)), dtype=float)
    train = pd.to_numeric(df[train_loss_col], errors="coerce")
    eval_loss = pd.to_numeric(df[eval_loss_col], errors="coerce") if eval_loss_col else None
    lr = pd.to_numeric(df[lr_col], errors="coerce") if lr_col else None
    # 首选 eval 侧指标（用于过拟合/背离判定）
    eval_metrics = [m for m in metrics if any(k in m.lower()
                    for k in ("eval", "val", "dev", "test"))] or metrics
    metric_col = eval_metrics[0] if eval_metrics else None
    metric = pd.to_numeric(df[metric_col], errors="coerce") if metric_col else None
    higher = _metric_higher_better(metric_col) if metric_col else True

    rules = [
        _rule_divergence(x, train),
        _rule_spikes(x, train),
        _rule_overfit(x, train, eval_loss, metric, metric_col, higher),
        _rule_underfit(x, train, metric, metric_col, higher),
        _rule_oscillation(x, train, lr),
        _rule_early_stop(x, eval_loss, metric, metric_col, higher),
        _rule_eval_lt_train(x, train, eval_loss),
        _rule_metric_loss_diverge(x, eval_loss, metric, metric_col, higher),
        _rule_constant_lr(x, lr, train),
    ]
    findings = [r for r in rules if r]
    sev_rank = {"高": 3, "中": 2, "低": 1, "提示": 0}
    n_high = sum(1 for f in findings if f["severity"] == "高")
    n_mid = sum(1 for f in findings if f["severity"] == "中")
    if n_high:
        rating = "高危：存在训练崩溃/明显病理，先处理高风险项再续训"
    elif n_mid:
        rating = "需关注：存在影响效果的中风险项，建议按处置建议调整后重训"
    elif findings:
        rating = "基本健康：无高危项，少量提示可参考"
    else:
        rating = "健康：曲线形态正常，可直接进入评估阶段"
    findings.sort(key=lambda f: -sev_rank.get(f["severity"], 0))
    return {"columns": cols, "x": x, "train": train, "eval_loss": eval_loss,
            "metric": metric, "metric_col": metric_col, "higher": higher,
            "lr": lr, "run_col": run_col, "findings": findings,
            "rating": rating, "n_steps": len(df)}


# ---------------------------------------------------------------------------
# 标注诊断图
# ---------------------------------------------------------------------------

_SEV_COLOR = {"高": "#c0392b", "中": "#e67e22", "低": "#27ae60", "提示": "#7f8c8d"}


def plot_diagnosis(diag, title=None, save_path=None):
    """按诊断结果绘制标注图：loss 主面板（问题区阴影+spike点+早停线）+ 指标副面板。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x, train, ev, m = diag["x"], diag["train"], diag["eval_loss"], diag["metric"]
    has_metric_panel = m is not None
    fig, axes = plt.subplots(2 if has_metric_panel else 1, 1,
                             figsize=(6.8, 4.6 if has_metric_panel else 3.8),
                             sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]} if has_metric_panel else None)
    if not has_metric_panel:
        axes = [axes]
    ax = axes[0]
    ax.plot(x, _finite(train), lw=1.4, color="#1a5fb4", label="train_loss", alpha=0.9)
    if ev is not None:
        ax.plot(x, _finite(ev), lw=1.4, color="#c0392b", label="eval_loss", alpha=0.9)
    ax.set_ylabel("loss")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(title or "训练曲线诊断", fontsize=11)

    labeled = set()
    for f in diag["findings"]:
        color = _SEV_COLOR.get(f["severity"], "#7f8c8d")
        if f.get("span"):
            ax.axvspan(f["span"][0], f["span"][1], color=color, alpha=0.10,
                       label="_" if "span" in labeled else "问题区间")
            labeled.add("span")
        for px in f.get("points", []):
            ax.axvline(px, color=color, ls=":", lw=1.0, alpha=0.7)
            ax.scatter([px], [float(_finite(train).iloc[(x - px).abs().idxmin()])],
                       color=color, s=36, zorder=5,
                       label="_" if "pt" in labeled else "异常点")
            labeled.add("pt")
        if f.get("vline"):
            ax.axvline(f["vline"], color="#27ae60", ls="--", lw=1.2,
                       label="_" if "vl" in labeled else "最佳/早停点")
            labeled.add("vl")
    if labeled:
        ax.legend(loc="upper right", fontsize=8, ncol=2)

    if has_metric_panel:
        ax2 = axes[1]
        ax2.plot(x, _finite(m), lw=1.4, color="#0b8a6d", label=diag["metric_col"])
        for f in diag["findings"]:
            if f.get("vline"):
                ax2.axvline(f["vline"], color="#27ae60", ls="--", lw=1.2)
            if f.get("span"):
                ax2.axvspan(f["span"][0], f["span"][1],
                            color=_SEV_COLOR.get(f["severity"], "#7f8c8d"), alpha=0.10)
        ax2.set_ylabel(diag["metric_col"])
        ax2.legend(loc="lower right", fontsize=8)
        ax2.set_xlabel(x.name or "epoch")
    else:
        ax.set_xlabel(x.name or "epoch")

    fig.tight_layout()
    out = Path(save_path) if save_path else DEFAULT_OUT / "diagnosis.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def build_report(diag, source_name, fig_rel):
    """生成 Markdown 诊断报告（风险卡片格式，report_html 可直接渲染）。"""
    lines = [f"# 训练曲线诊断报告（{source_name}）",
             "",
             f"- 数据文件：`{source_name}`（{diag['n_steps']} 步）",
             "- 生成方式：academic-research 技能 train_doctor 模块（确定性规则引擎）",
             "- 声明：诊断为规则化形态判读，证据已随附；处置决策权归研究者",
             "",
             "## 总体评级",
             "",
             f"**{diag['rating']}**",
             ""]
    if diag["findings"]:
        lines += ["| # | 风险 | 诊断 | 关键证据 |", "|---|---|---|---|"]
        for i, f in enumerate(diag["findings"], 1):
            lines.append(f"| {i} | {f['severity']} | {f['title'].split('：')[0]} | {f['evidence'][:60]}… |")
        lines.append("")
    lines += ["## 诊断明细", ""]
    if not diag["findings"]:
        lines += ["曲线形态正常：loss 单调收敛、无 spike、eval 侧未见恶化拐点。", ""]
    for f in diag["findings"]:
        lines += [f"### [风险等级：{f['severity']}] {f['title']}",
                  "",
                  f"- 证据：{f['evidence']}",
                  f"- 建议：{f['suggestion']}",
                  ""]
    lines += ["## 标注诊断图", "",
              f"![训练曲线诊断标注图]({fig_rel})",
              "",
              "> 阴影区间=问题区域；虚线=最佳 checkpoint / 建议早停点；点标记=异常点。",
              "",
              "## 人工复核清单",
              "",
              "- [ ] 证据 epoch 与原始日志逐条对照（规则引擎可能受日志记录间隔影响）",
              "- [ ] spike 步对应 batch 数据抽样人工检查",
              "- [ ] 早停建议与磁盘中的 checkpoint 策略核对",
              "- [ ] eval<train 倒置情况做一次 eval 集泄漏抽查",
              "",
              "> AI生成"]
    return "\n".join(lines)


def _save_recipe(diag, csv_path, out_dir, report_path, fig_path):
    """结构化诊断结论 + 数据指纹存档（复现核对用）。"""
    rec = {"tool": "train_doctor", "version": "3.0.0",
           "input": str(csv_path),
           "data_md5": hashlib.md5(Path(csv_path).read_bytes()).hexdigest(),
           "n_steps": diag["n_steps"], "rating": diag["rating"],
           "columns": {k: v for k, v in diag["columns"].items()},
           "findings": [{"code": f["code"], "severity": f["severity"],
                         "title": f["title"], "evidence": f["evidence"],
                         "suggestion": f["suggestion"]} for f in diag["findings"]],
           "outputs": {"report": str(report_path), "figure": str(fig_path)}}
    p = out_dir / (Path(csv_path).stem + ".diagnosis.json")
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def run(csv_path, out_dir=None, html=False, **col_overrides):
    """端到端：CSV → 诊断 → 图 → 报告（+可选 HTML）。返回输出路径 dict。"""
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT / csv_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # 多 run 日志：按 run 列拆分逐一诊断
    pre_cols = detect_columns(df)
    run_col = col_overrides.get("run_col") or pre_cols["run"]
    results = {}
    if run_col and df[run_col].nunique() > 1:
        for name, sub in df.groupby(run_col):
            results[name] = _diagnose_one(sub.reset_index(drop=True), csv_path,
                                          out_dir, html, tag=str(name),
                                          **col_overrides)
        return results
    return _diagnose_one(df, csv_path, out_dir, html, **col_overrides)


def _diagnose_one(df, csv_path, out_dir, html, tag=None, **col_overrides):
    suffix = f"_{tag}" if tag else ""
    diag = diagnose(df, **{k: v for k, v in col_overrides.items() if v})
    fig_path = out_dir / f"诊断标注图{suffix}.png"
    plot_diagnosis(diag, title=f"训练曲线诊断{('·'+tag) if tag else ''}",
                   save_path=fig_path)
    report_path = out_dir / f"训练曲线诊断报告{suffix}.md"
    report_path.write_text(build_report(diag, csv_path.name, fig_path.name),
                           encoding="utf-8")
    recipe = _save_recipe(diag, csv_path, out_dir, report_path, fig_path)
    out = {"report": report_path, "figure": fig_path, "diagnosis": recipe}
    if html:
        from report_html import render_file
        out["html"] = render_file(report_path)
    return out


# ---------------------------------------------------------------------------
# 演示入口：四种典型病理样例
# ---------------------------------------------------------------------------

def _demo():
    samples = SKILL_ROOT / "samples"
    cases = [
        ("demo_trainlog_healthy.csv", "健康基线：正常收敛应零检出"),
        ("demo_trainlog_overfit.csv", "过拟合：eval_loss 拐点回升"),
        ("demo_trainlog_lr_high.csv", "学习率过高：全程振荡"),
        ("demo_trainlog_spike.csv", "Loss spike：单点突跳"),
    ]
    for fname, desc in cases:
        p = samples / fname
        if not p.exists():
            print(f"[缺样例] {fname} 不存在，跳过")
            continue
        print(f"\n■ {fname} —— {desc}")
        out = run(p, html=True)
        print("  报告:", out["report"])
        print("  图  :", out["figure"])
        print("  HTML:", out.get("html"))


def main(argv=None):
    try:  # Windows GBK 控制台无法编码 ✓/⚠ 等符号：替换而非崩溃（v2.1.1）
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="大模型微调训练曲线诊断器（规则引擎+标注图+体检报告）")
    ap.add_argument("csv", nargs="?", help="训练日志 CSV（epoch + train_loss/eval_loss/指标/lr）")
    ap.add_argument("--epoch-col", default=None, help="步数列名（默认自动识别 epoch/step）")
    ap.add_argument("--train-loss", dest="train_loss_col", default=None,
                    help="训练损失列名（默认自动识别 train_loss/loss）")
    ap.add_argument("--eval-loss", dest="eval_loss_col", default=None,
                    help="验证损失列名（默认自动识别 eval_loss/val_loss 等）")
    ap.add_argument("--lr-col", default=None, help="学习率列名（可选）")
    ap.add_argument("--run-col", default=None, help="多 run 分组列名（可选，自动拆分）")
    ap.add_argument("--out", default=None, help="输出目录（默认 .temp/train_doctor/<文件名>/）")
    ap.add_argument("--html", action="store_true", help="追加单文件 HTML 诊断报告")
    ap.add_argument("--demo", action="store_true", help="四种典型病理样例全量自验")
    args = ap.parse_args(argv)
    if args.demo:
        _demo()
        return
    if not args.csv:
        ap.print_help()
        return
    out = run(args.csv, out_dir=args.out, html=args.html,
              epoch_col=args.epoch_col, train_loss_col=args.train_loss_col,
              eval_loss_col=args.eval_loss_col, lr_col=args.lr_col,
              run_col=args.run_col)
    print("诊断完成：")
    for k, v in (out.items() if isinstance(out, dict) else []):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
