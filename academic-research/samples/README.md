# samples/ 示例数据说明

本目录数据均为**人工构造的演示数据**（随机种子固定，可复现），仅用于：

1. `tools/` 下各脚本的功能验证与演示
2. 演示视频中的演示素材

**不得用于任何论文、报告的真实实验结论**。正式分析请使用你自己的实验数据。

场景设定（v3.0 起）：数据按研究课题**「低资源条件下微调实验结论的稳健性研究——以电信告警分类为例」**组织——三个研究问题：RQ1 单 seed 结论稳健性（结论翻转率）、RQ2 训练病理与泛化相关性、RQ3 精度-成本权衡。列名保持通用（model/dataset），语义映射见下表。

| 文件 | 内容 | 场景语义（服务的研究问题） | 对应工具 |
|---|---|---|---|
| `demo_finetune_results.csv` | 基座零样本 + 4 种微调策略的 acc/f1/loss/延迟（mean±std） | 策略横向对比（RQ3 成本列） | experiment_table（对比表 + Δ列） |
| `demo_ablation.csv` | 数据清洗/调度/早停组件开关 × 精度 | LoRA 消融实验 | experiment_table（消融表 ✓/✗） |
| `demo_trainlog_healthy.csv` | 60 epoch 正常收敛训练日志 | 健康基线（RQ2 变量素材） | train_doctor |
| `demo_trainlog_overfit.csv` | eval_loss 第 34 epoch 后回升 | 过拟合病理（RQ2） | train_doctor |
| `demo_trainlog_lr_high.csv` | 全程剧烈振荡 + 恒定高 lr | 学习率过高病理（RQ2） | train_doctor |
| `demo_trainlog_spike.csv` | 第 28/44 epoch 两次突跳 | Loss spike 病理（RQ2） | train_doctor |
| `demo_group_comparison.csv` | 4 任务 × 3 策略 × 5 seeds 的测试准确率（长表） | **RQ1 核心数据**：单 seed 排序 vs 多 seed 均值（告警任务 seed2 存在真实结论翻转） | grouped_bar / grouped_box / violin / qq_plot / three_line_table / AutoReport / **robustness_check** |
| `demo_correlation.csv` | 微调训练样本量与测试准确率、训练时长（40 次实验） | 数据规模规律 | scatter_fit / plot_line / AutoReport |
| `demo_metrics.csv` | 36 种配置的深度/宽度/参数量/FLOPs/准确率/时延 | 模型规格与成本 | heatmap（先 `df.corr()`）/ radar |
| `demo_training_curve.csv` | 3 策略 × 60 epoch 的验证准确率与损失（单曲线） | 训练曲线 | plot_line |
| `demo_binary_classification.csv` | 3 模型 × 300 样本的二分类预测（y_true/y_score/y_pred） | 分类评估 | roc_curves / pr_curves / confusion_matrix / AutoReport |
| `demo_training_multi_seed.csv` | 3 策略 × 3 seed × 25 轮的多 seed 训练记录 | 多 seed 稳定性（RQ1 可视化） | line_band（误差带折线） |
| `demo_trainlog_multi_run.csv` | 18 个 run 的训练日志（含 run 列：7 健康/4 过拟合/3 spike/3 振荡/1 发散） | **RQ2 变量化素材** | pathology_correlate（批量诊断） |
| `demo_run_results.csv` | 18 个 run 的最终准确率（病理重=精度低，相关性真实存在） | RQ2 结局变量 | pathology_correlate（相关分析） |
| `demo_citations_mixed.txt` | 20 条混乱引文（三种来源风格，含标准号/专利/纯URL等边界条目） | 参考文献整理 | citation_formatter / citation_verifier |
| `demo_proposal_draft.md` | 虚构申报书草稿（内置 13 处典型问题，附对照表）——仅供体检演示，请勿套用 | 申报书体检 | proposal-nsfc.md 体检线 |

一键验证：
- `python tools/plot_templates.py --demo`（十二张图）
- `python tools/three_line_table.py --demo`（Word 三线表）
- `python tools/auto_report.py samples/demo_group_comparison.csv --yes`（一键分析）
- `python tools/train_doctor.py --demo`（四种训练病理诊断）
- `python tools/experiment_table.py --demo`（对比表 + 消融表 + 指标图）
- `python tools/robustness_check.py --demo`（结论翻转率 + 最少seed数，两任务对照）
- `python tools/pathology_correlate.py --demo`（18 run 病理×泛化相关分析）
- `python tools/citation_formatter.py --demo`（引文批量格式化）
- `python tools/citation_verifier.py --demo`（引文核验+元数据补全，需网络）
- `python tools/citation_verifier.py samples/demo_citations_mixed.txt --year-report`（年份结构体检，不联网）

> AI生成
