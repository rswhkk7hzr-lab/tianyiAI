# samples/ 示例数据说明

本目录数据均为**人工构造的演示数据**（随机种子固定，可复现），仅用于：

1. `tools/plot_templates.py` 的功能验证与演示
2. 演示视频中的演示素材

**不得用于任何论文、报告的真实实验结论**。正式分析请使用你自己的实验数据。

| 文件 | 内容 | 对应模板 |
|---|---|---|
| `demo_group_comparison.csv` | 4 个数据集 × 3 种模型 × 5 个随机种子的测试准确率（长表） | grouped_bar / grouped_box / violin / qq_plot / three_line_table / AutoReport |
| `demo_correlation.csv` | 训练样本量与测试准确率、训练时长（40 次实验） | scatter_fit / plot_line / AutoReport |
| `demo_metrics.csv` | 36 种模型配置的深度/宽度/参数量/FLOPs/准确率/时延等指标 | heatmap（先 `df.corr()`）/ radar |
| `demo_training_curve.csv` | 3 种模型 × 60 epoch 的验证准确率与损失（单曲线） | plot_line |
| `demo_binary_classification.csv` | 3 个模型 × 300 样本的二分类预测结果（y_true/y_score/y_pred） | roc_curves / pr_curves / confusion_matrix / AutoReport |
| `demo_training_multi_seed.csv` | 3 模型 × 3 seed × 25 轮的多 seed 训练记录 | line_band（误差带折线） |

一行验证：`python tools/plot_templates.py --demo`（十二张图）
三线表验证：`python tools/three_line_table.py --demo`
一键分析验证：`python tools/auto_report.py samples/demo_group_comparison.csv --yes`
