---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '9f3c71a2-4b6d-4e8f-a1c5-2d7e9b0f3a41'
  PropagateID: '9f3c71a2-4b6d-4e8f-a1c5-2d7e9b0f3a41'
  ReservedCode1: 'fd38291b-aa23-482b-922d-c13fbe9000b3'
  ReservedCode2: 'fd38291b-aa23-482b-922d-c13fbe9000b3'
---

# 大模型微调实验方法学指南

## 目录
1. 研究问题与适用边界
2. 实验设计规范（对比矩阵 / 超参 / 消融 / 稳健性协议）
3. 训练监控与曲线诊断（train_doctor 工作流）
4. 评估规范（多 seed / 显著性 / 泄漏红线）
5. 实验表格产出（experiment_table 工作流）
6. 演示数据与场景样例
7. 与七模块的流水线衔接

## 1. 研究问题与适用边界

本指南面向**垂直场景的大模型微调实验研究**，演示课题为：

> **「低资源条件下微调实验结论的稳健性研究——以电信告警分类为例」**

这不是"用微调做个分类器"的应用题，而是一个**实验方法学研究**：以电信告警工单分类为载体任务，回答三个有张力的研究问题——

| # | 研究问题 | 性质 | 主要工具 |
|---|---------|------|---------|
| **RQ1**（主线） | 低资源场景下单次运行的微调结论可信吗？"LoRA 优于 QLoRA"这类结论在不同随机种子下会翻转吗？要多少 seed 结论才稳？ | 可复现性方法学：单 seed 结论 → 多 seed 检验 → 结论翻转率量化 | experiment_table / auto_report / line_band |
| **RQ2**（暗线） | 训练病理模式（过拟合/spike/振荡/早停）与最终泛化性能是否存在相关性？能否用训练曲线症状提前预测实验成败？ | 以 train_doctor 诊断为自变量的相关性分析——**工具输出即研究数据** | train_doctor（诊断→变量化）+ 统计检验 |
| **RQ3**（应用） | 在显存/延迟预算约束下，四种策略的精度-成本权衡前沿在哪？ | 工程选型决策，落点是可执行的策略推荐表 | experiment_table（latency/vram 列）+ plot_templates |

- **覆盖**：Full-FT / LoRA / QLoRA / Prefix-Tuning 的实验设计、训练诊断、多 seed 稳健性评估、消融归因、结论可信度量化；
- **不覆盖**：预训练语料工程、RLHF/DPO 细节、分布式训练运维——超边界需求如实告知；
- **配套工具**：`tools/train_doctor.py`（训练曲线诊断）、`tools/experiment_table.py`（对比/消融表）、`tools/auto_report.py`（多 seed 统计分析）、`tools/plot_templates.py`（曲线/评估图）、`tools/three_line_table.py`（Word 三线表）。

**RQ2 为什么是本技能的独特价值**：通用 AI 看训练曲线只能给印象级判断，无法把"症状"变成可统计的变量。train_doctor 把每条诊断落成 `.diagnosis.json`（病理类型/等级/epoch 区间），可直接作为相关性分析的自变量——**诊断器的输出不是终点，而是研究的起点**。这条暗线在答辩时是最难被"你这和豆包有什么区别"击倒的一击。

## 2. 实验设计规范

### 2.1 对比矩阵设计

论文级微调实验至少覆盖三个对比维度，缺一会被审稿人追问：

| 维度 | 必选项 | 说明 |
|---|---|---|
| 基线 | 基座零样本 / 上一 SOTA / 传统方法 | 无基线的提升数字无意义 |
| 微调策略 | Full-FT、LoRA、QLoRA、Prefix-Tuning ≥2 种 | 精度-显存-耗时权衡是微调论文核心 |
| 消融 | 一次一因子（数据清洗/调度/早停/r 值/target 模块） | 组件贡献归因 |

### 2.2 超参报告清单（论文必须给出的）

- 基座模型与版本、参数量、上下文长度；
- 微调策略及关键超参：LoRA r / alpha / dropout / target_modules；lr 与调度器（cosine/linear + warmup ratio）；epoch；batch（含梯度累积折算）；max_seq_len；
- 硬件与精度：GPU 型号、bf16/fp16、显存占用；
- **数据**：训练/验证/测试集规模、来源、清洗规则、标注一致性（人工数据）。

### 2.3 消融设计原则

- 一次只变一个因子，其余冻结；
- 每个消融臂与主配置同 seed 集合，保证差值可归因；
- 消融结论只陈述"移除 X 导致指标变化 Δ"，归因解释归讨论节。

### 2.4 多 seed 规范与稳健性协议（RQ1 操作化）

- 关键结果 ≥3 seeds（学位论文/期刊建议 5），报告均值±标准差；
- 组间差异结论必须做显著性检验（→ `auto_report.py` 自动按决策表选检验）；
- 训练稳定性用 `plot_templates.py` 的 `line_band`（多 seed 均值±标准差误差带）呈现；
- **结论翻转率分析（RQ1 核心）**：对每个 seed 单独算策略排序，统计"单 seed 结论 ≠ 多 seed 均值结论"的翻转比例——这是"单 seed 结论可信吗"的量化答案，是课题的主要贡献点；
- **配对设计**：比较两策略差异时按 seed 配对（paired test），消掉种子效应，统计功效更高——`auto_report.py` 的数据表按 (seed, model) 长表组织即天然支持。

## 3. 训练监控与曲线诊断（train_doctor 工作流）

### 3.1 为什么用规则引擎而不是"让大模型看一眼曲线"

通用 AI 看曲线给的是印象级判断（"好像有点过拟合"），不可复现、无证据、每次说法不一。`train_doctor.py` 把训练病理转化为**确定性规则**：每条结论附 epoch 区间与数值证据，同一份日志永远得到同一份诊断——这是实验纪律，也是对通用 AI 的差异化能力。

### 3.2 用法

```bash
# 零参数：自动识别 epoch/train_loss/eval_loss/指标/lr 列，输出三件套
python tools/train_doctor.py 训练日志.csv
# 追加单文件 HTML 体检报告（可投屏/发送）
python tools/train_doctor.py 训练日志.csv --html
# 列名不规范时显式指定
python tools/train_doctor.py 日志.csv --train-loss loss --eval-loss dev_loss --epoch-col step
# 多 run 日志：自动按 run/config 列拆分逐一诊断
python tools/train_doctor.py 多配置日志.csv
# 自验（四种典型病理样例）
python tools/train_doctor.py --demo
```

输出：诊断报告（总体评级+风险卡片明细）+ 标注诊断图（问题区间阴影/spike 点/早停线）+ `.diagnosis.json`（结构化结论与数据指纹，可复现核对）。

### 3.3 判据速查（报告口径）

| 检出 | 判据摘要 | 处置方向 |
|---|---|---|
| 训练发散 | loss NaN/Inf 或 >10×初始 | 降 lr、grad clip、查数据、bf16 |
| Loss spike | 相对前窗中位数跳变 >4×稳健尺度且 >15% | 脏 batch 排查、grad clip、warmup |
| 过拟合 | eval_loss 平滑拐点后回升 >8% 且超噪声 | 按拐点早停、数据/正则增强、降容量 |
| 欠拟合 | 双侧高位平台 | 加容量/epoch、调 lr、查数据质量 |
| 未收敛 | 末段仍快速下降 | 加 epoch 或升 lr |
| 振荡偏大 | 差分抖动 >8% 净降幅 | 降 lr、加 batch/累积、warmup |
| 早停建议 | 最佳 eval 点 <70% 进度 | early_stopping + patience |
| eval<train 倒置 | 后半程 eval 中位数 <90% train | 正则不对称良性/泄漏抽查 |
| 指标-loss 背离 | 末 1/3 走势相反 | 评估口径与同分布核查 |
| 恒定 lr+平台 | lr 恒定且末段 <5% 幅度 | cosine/step 衰减建议 |

### 3.4 诊断输出变量化（RQ2 操作化）

train_doctor 的 `.diagnosis.json` 不只是体检报告，还是**相关性分析的数据源**：

```bash
# 批量诊断：对每个 run 的训练日志逐一产出 .diagnosis.json
for f in runs/*.csv; do python tools/train_doctor.py "$f"; done
```

收集各 run 的 `findings[].type`（overfit/spike/oscillation/healthy）、`severity`、`epoch` 与最终测试指标，整理为 (run, pathology_type, severity, test_acc) 长表，即可用 auto_report / 列联表 / 点二列相关检验"病理×泛化"相关性。例如：检出过拟合的 run 平均 acc 是否显著低于健康 run？spike 是否预示最终 loss 更高？

### 3.5 人工复核纪律

规则引擎出"嫌疑"，人出"结论"：诊断报告每项须对照原始日志复核证据 epoch；spike 步抽样检查对应 batch；eval<train 倒置做一次泄漏抽查后再下结论。诊断器不替研究者做最终判断。

## 4. 评估规范

### 4.1 指标选择

- 分类任务：Accuracy + 宏 F1（类不平衡时以 F1 为主）+ 混淆矩阵呈现错误结构；
- 生成任务：ROUGE/BLEU 仅作参考，必须配人工评估（维度：正确性/流畅性/领域合规）；
- 运维场景加延迟/显存成本列（精度-成本权衡是微调策略对比的核心叙事）。

### 4.2 报告口径

- 均值±标准差，注明 seed 数；
- 显著性：两组比较按决策表选 t 检验/Mann-Whitney，三组以上 ANOVA/Kruskal-Wallis——`auto_report.py --group method --value acc` 自动执行；
- 分类评估图三件套：`roc_curves`/`pr_curves`/`confusion_matrix`（`samples/demo_binary_classification.csv` 即插即用）。

### 4.3 数据泄漏红线

- eval/test 集绝不参与训练与超参选择；超参选择只用 validation；
- 微调数据与 benchmark 测试集做去重核查（近重复也算泄漏）；
- 在论文方法节如实写明去重与划分规则——审稿人会查。

## 5. 实验表格产出（experiment_table 工作流）

```bash
# 对比表：自动识别 method+指标列、mean±std 合并、最优加粗
python tools/experiment_table.py 结果.csv
# 加基线 Δ 提升量列
python tools/experiment_table.py 结果.csv --baseline "Full-FT" --delta
# 消融表：组件开关列自动 ✓/✗，因子列原样呈现
python tools/experiment_table.py 消融.csv --components "data_clean,cosine_lr,early_stop"
python tools/experiment_table.py 消融.csv --factor-cols "r,alpha,dropout"
# 自验
python tools/experiment_table.py --demo
```

- 指标方向推断：`loss/err/latency/time/params/flops/memory` 按越小越好，其余越大越好；`--metrics "acc:max,loss:min"` 可显式覆盖；
- 输出 Word 三线表（最优值加粗，直接入论文）+ Markdown 预览（随附 `.md` 可核对）；
- 表格口径纪律：最优加粗仅限单指标列内比较；Δ 列相对指定基线；表注写明 seed 数与统计口径。

## 6. 演示数据与场景样例

`samples/` 按"低资源条件下电信告警分类微调稳健性研究"场景组织（人工构造，虚构标注，仅用于功能验证）：

| 文件 | 场景语义 | 服务的研究问题 | 配套工具 |
|---|---|---|---|
| demo_finetune_results.csv | 四策略+基座零样本的 acc/f1/loss/延迟 | RQ3 精度-成本权衡 | experiment_table 对比表 |
| demo_ablation.csv | 数据清洗/调度/早停组件开关 | 消融归因 | experiment_table 消融表 |
| demo_group_comparison.csv | 4 任务×3 策略×5 seeds 精度（长表） | **RQ1 稳健性核心数据**：单 seed 排序 vs 多 seed 均值 | auto_report / grouped_box |
| demo_trainlog_{healthy,overfit,lr_high,spike}.csv | 四种典型训练病理日志 | **RQ2 变量化素材**：诊断标签→相关性分析 | train_doctor 诊断 |
| demo_training_multi_seed.csv | 3 策略×3 seed×25 轮训练记录 | RQ1 稳定性可视化 | line_band |
| demo_training_curve.csv | 3 策略×60 epoch 验证曲线 | 训练过程展示 | plot_line |
| demo_binary_classification.csv | 分类评估（y_true/y_score） | 评估结构 | ROC/PR/混淆矩阵 |
| demo_correlation.csv | 训练样本量→精度规律 | 数据规模效应 | scatter_fit |
| demo_metrics.csv | 36 种配置的参数量/FLOPs/准确率/时延 | RQ3 成本维度 | heatmap / radar |

**演示叙事提示**：用 demo_group_comparison 现场演示 RQ1——先按单 seed 切片展示"结论恰好翻转"（如某 seed 下 QLoRA 反超 LoRA），再展示 5 seed 均值±std 的稳定排序与显著性检验——"换一批种子结论就变"这一帧是稳健性研究最有冲击力的演示瞬间。

## 7. 与七模块的流水线衔接

微调实验不是孤立的，本指南是流水线的"实验段"：

```
选题综述(模块一) → 实验设计(本指南§2) → 训练监控(train_doctor§3)
   → 结果分析与统计(模块二+auto_report) → 实验表格(experiment_table§5)
   → 论文写作润色(模块四) → 参考文献核验(模块三) → 投稿自审(模块七)
   → 申报场景: 申报书撰写与体检(模块五)；交付: 文档导出(模块六)
```

- 实验前的"相关工作/基线调研"按模块一执行；
- 实验表格与图件按模块二/六的规范进入论文；
- 涉及参考文献的结果对比表，文献条目过模块三核验；
- 投稿前对照模块七 rubric 检查"实验充分性"维度（本指南 §2 矩阵即其操作化）。

> AI生成
