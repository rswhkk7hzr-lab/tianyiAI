---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'f555bb65-5281-4e12-8627-9a2b73132bab'
  PropagateID: 'f555bb65-5281-4e12-8627-9a2b73132bab'
  ReservedCode1: '7a407d24-7417-4e62-ad54-3b5313e20684'
  ReservedCode2: '7a407d24-7417-4e62-ad54-3b5313e20684'
---

# 数据分析可视化指南

## 目录
1. 分析前：数据质量检查
2. 统计方法选择决策表
3. 图表类型选择
4. 学术图表通用规范
5. matplotlib 实施规范（含出图模板脚本）
6. 三线表规范（含生成脚本）
7. 统计分析报告规范与自检清单
8. AutoReport：CSV 一键分析报告
9. 图表规范体检（智能体工作流）
10. 机制图/通路图绘制规范
11. 证据综合图（森林图/漏斗图/剂量-反应曲线）

## 0. 领域内落点（微调实验结论稳健性课题）

本课题的典型数据形态：多 seed 结果长表（method × seed × metric）、训练日志（epoch × loss/metric）、消融开关表。优先图表：`line_band` 多 seed 误差带、`grouped_box` 分组箱线（稳健性直观证据）、`robustness_check` 名次 bump 图与稳定性曲线、`pathology_correlate` 病理分组对比图。统计口径：组间比较按 seed 配对（paired t/Wilcoxon），多组用 ANOVA/Kruskal——`auto_report.py` 按长表直接执行。**先跑 `robustness_check.py` 确认结论稳健，再决定图怎么画**——不稳的结论画图再漂亮也是误导。

## 1. 分析前：数据质量检查

绘图与检验之前先完成下表，检查结果与处理方式须如实写入报告（不得静默删除或改动数据）：

| 检查项 | 方法 | 处置原则 |
|---|---|---|
| 变量结构 | 查看列名、类型、单位、样本量 n | 类型错误的先修正（如数值被读成字符串） |
| 缺失值 | 各列缺失比例 + 缺失模式（随机/系统） | 删除或插补（均值/中位数/多重插补）须注明；缺失>20% 的变量慎用 |
| 离群值 | 1.5×IQR 法或 Z 分数（\|Z\|>3） | 只标记并说明，不静默删除；删除必须报告"删除了几条、依据是什么" |
| 正态性 | Shapiro-Wilk（n<50，逐组检验）；Kolmogorov-Smirnov（n≥50） | 不满足正态 → 改用非参数方法（见第 2 节），不要强行 t 检验 |
| 方差齐性 | Levene 检验（组间比较前必查） | 不齐 → Welch t 检验 / Welch ANOVA，并在报告中注明 |
| 量纲一致性 | 检查单位与数量级 | 回归/聚类前考虑标准化（z-score），并注明 |

**红线**：不得为"结果好看"而剔除数据点；任何预处理必须可复现、可说明。

## 2. 统计方法选择决策表

按"数据类型 → 比较目的 → 前提是否满足"三步查表选择（覆盖绝大多数科研场景）：

### 2.1 组间比较

| 数据情形 | 2 组独立 | 2 组配对 | ≥3 组独立 |
|---|---|---|---|
| 连续 + 正态 + 方差齐 | 独立样本 t 检验 | 配对样本 t 检验 | 单因素 ANOVA + 事后检验（Tukey HSD） |
| 连续 + 正态 + 方差不齐 | Welch t 检验 | — | Welch ANOVA + Games-Howell 事后 |
| 连续 + 非正态 | Mann-Whitney U | Wilcoxon 符号秩 | Kruskal-Wallis + Dunn 事后 |
| 分类（构成比） | 卡方检验（期望频数均≥5） | McNemar 检验 | 卡方检验 |
| 分类（期望频数<5） | Fisher 精确检验 | — | 合并类别或 Fisher（R×C） |

### 2.2 关联与预测

| 分析目的 | 前提满足 | 前提不满足/有序数据 |
|---|---|---|
| 两连续变量关联 | Pearson 相关 | Spearman 秩相关 |
| 多自变量预测连续结局 | 多元线性回归（查残差正态、无多重共线 VIF<10） | 数据变换（log/Box-Cox）或非参数/稳健回归 |
| 连续变量随自变量变化 | 一元/多项式回归（先看散点定阶数） | LOWESS / Theil-Sen 稳健拟合 |

**多重比较警示**：同一数据做多组两两比较时，必须校正（Bonferroni 或 FDR），否则Ⅰ类错误膨胀；校正方法写入报告。

## 3. 图表类型选择

按数据关系选图，不确定时与用户确认：

| 分析目的 | 推荐图表 | 备注 |
|---|---|---|
| 单变量分布 | 直方图、核密度图、箱线图 | 箱线图适合多组对比 |
| 组间比较 | 柱状图、分组柱状图、雷达图 | 误差线必须标注（标准差/标准误/置信区间，图注说明） |
| 两变量关系 | 散点图（可加拟合线） | 三变量用气泡图或分面 |
| 趋势演变 | 折线图 | 多组趋势用不同线型+标记 |
| 构成占比 | 堆叠柱状图 | 慎用饼图（类别>5 禁用） |
| 相关矩阵 | 热力图 | 标注相关系数 |
| 多指标对比 | 雷达图 | 指标≤8 个 |
| 流程/机制 | 流程图/示意图 | 用 diagram-drawing 相关能力或绘制 |

## 4. 学术图表通用规范

- **分辨率**：位图 ≥300 DPI（印刷）；矢量格式（PDF/SVG/EPS）优先于位图
- **尺寸**：单栏图宽约 8 cm（3.15 in），双栏通栏约 17 cm；按目标期刊调整
- **坐标轴**：物理量 + 单位，格式"量符号/(单位)"，如"速度 v/(m·s⁻¹)"；无量纲量只写名称
- **字号**：图内文字（刻度、图例、标注）≥9 pt，成图缩放后仍可读
- **配色**：黑白打印友好（结合线型/填充纹理区分）+ 色盲友好；同组数据同色系
- **图注**：图注置图下方，表注置表上方；格式"图1 xxx的xxx结果"（句末无标点）；多子图用（a）（b）标注
- **正文交叉引用**：每个图表必须在正文中被引用和解读，不能只贴不解

## 5. matplotlib 实施规范（含出图模板脚本）

### 5.1 首选方式：调用本技能自带模板脚本

常规学术图表优先用 `tools/plot_templates.py`（相对本技能目录），脚本自动定位 `assets/academic.mplstyle` 学术样式，**无需手写样式路径**：

```python
import sys
sys.path.insert(0, r"<本技能目录>/tools")   # 技能目录见技能加载信息
import plot_templates as pt
import pandas as pd

df = pd.read_csv(r"<本技能目录>/samples/demo_group_comparison.csv")

# 统计基础图（5 个）
pt.grouped_bar(df, x="dataset", y="accuracy", group="model", yerr="std",
               ylabel="准确率/(%)", save_path=r".temp\图1.png")
pt.grouped_box(df, x="dataset", y="accuracy", group="model", save_path=r".temp\图2.png")
pt.scatter_fit(df2, x="train_samples", y="accuracy", fit="linear", save_path=r".temp\图3.png")
pt.heatmap(corr_df, title="指标相关矩阵", save_path=r".temp\图4.png")
pt.plot_line(df3, x="epoch", y="val_accuracy", group="model", best="max",
             xlabel="训练轮次/epoch", ylabel="验证准确率/(%)", save_path=r".temp\图5.png")

# 分布与诊断图（2 个）
pt.violin(df, x="model", y="accuracy", save_path=r".temp\图6.png")      # 含自动显著性星号
pt.qq_plot(df, y="accuracy", group="dataset", save_path=r".temp\图7.png")  # 正态性诊断+Shapiro p值

# 分类评估图（3 个）
pt.roc_curves(dfc, label_col="y_true", score_col="y_score", model_col="model",
              save_path=r".temp\图8.png")   # 自动AUC+随机基线
pt.pr_curves(dfc, label_col="y_true", score_col="y_score", model_col="model",
             save_path=r".temp\图9.png")   # 自动AP+随机基线
pt.confusion_matrix(dfc, true_col="y_true", pred_col="y_pred",
                    normalize=True, save_path=r".temp\图10.png")  # 自动P/R/F1

# 综合对比图（2 个）
pt.radar(dfm, metrics=["acc", "flops", "latency"], model_col="model",
         higher_is_better={"latency": False}, save_path=r".temp\图11.png")
pt.line_band(dfms, x="epoch", y="val_accuracy", group="model",
             save_path=r".temp\图12.png")  # 多seed均值±带

# 风格预设（投稿前一键切换）
pt.set_style_preset("journal")      # 黑白期刊版；另可选 thesis（彩色）/ colorblind（色盲友好）
```

脚本内置十二类模板（函数签名详见 docstring）：

| 类别 | 模板 | 亮点 |
|---|---|---|
| 统计基础 | grouped_bar / grouped_box / scatter_fit / heatmap / plot_line | 误差线自动聚合；相关系数自动标注；最优点自动标注 |
| 分布诊断 | violin / qq_plot | **自动显著性星号线**（两两检验按决策表自动选方法）；Q-Q 图附 Shapiro-Wilk p 值（前提检验可视化） |
| 分类评估 | roc_curves / pr_curves / confusion_matrix | 自动 AUC/AP；随机基线；混淆矩阵附各类 P/R/F1 |
| 综合对比 | radar / line_band | 多指标归一化对比（小指标自动反向）；多 seed 稳定性带 |

**通用能力**（全部模板共享）：
- `save_pdf=True`：一次输出同名 PNG（300 DPI 位图）+ PDF（矢量版，期刊投稿用，样式已配置 fonttype=42）；
- **绘图配方存档**：每次出图自动落盘同名 `.recipe.json`（模板名/参数/数据 MD5 指纹/输出路径），论文返修改数据后可核对图形与数据是否同步，支持一键复现；
- **图注自动生成**：violin / line_band 等模板返回 `caption` 字段（规范图注文字），可直接用于论文排版；
- **风格预设**：`set_style_preset("journal"/"thesis"/"colorblind")` 一键切换黑白期刊/彩色论文/色盲友好配色；
- **颜色/样式快速自定义**（v1.3.1，约定优于配置）：所有模板暴露 `colors`（多系列图）或 `color`（单系列图）参数，热力图/混淆矩阵暴露 `cmap`。默认值=学术规范，想改一行搞定：

```python
# 用法1：十六进制颜色列表（按分组顺序对应）
pt.grouped_bar(df, x="dataset", y="accuracy", group="model",
               colors=["#4C72B0", "#DD8452", "#55A868"])

# 用法2：颜色名字符串（matplotlib 全部命名色可用，单色统一）
pt.violin(df, x="model", y="accuracy", colors="steelblue")

# 用法3：短列表自动循环（2 色循环 3 个模型）
pt.roc_curves(df, label_col="y_true", score_col="y_score", model_col="model",
              colors=["darkorange", "purple"])

# 用法4：不传参数 → 默认学术色板（黑白打印友好），完全不受影响
```

  常用颜色参考：蓝 `#4C72B0` / 橙 `#DD8452` / 绿 `#55A868` / 红 `#C44E52` / 紫 `#8172B3`；颜色名如 `steelblue`、`crimson`、`darkorange`、`teal`；搭配好的科研配色可搜索 seaborn color palette（如 "deep"/"muted"）取色值。自定义颜色时注意保持黑白打印可辨（亮度差异足够）与色盲友好（避免红绿同图）；

- **视觉参数快速微调**（v1.3.2，默认即满意初版、微调只改参数不改代码）：

| 参数 | 作用 | 典型用法 |
|---|---|---|
| `figsize` | 图幅 | 预设名 `"single"`(默认)/`"double"`(双栏通栏)/`"square"`(方图)/`"slide"`(答辩宽屏)/`"half"`(半高)，或 `(宽,高)` 元组 |
| `font_scale` | 全局字号缩放 | 答辩大图 `font_scale=1.4`，投影后排仍可读 |
| `legend_loc` | 图例位置 | `"upper left"` / `"best"` 等 matplotlib 位置串 |
| `xlim` / `ylim` | 轴范围 | 聚焦区间、统一多图刻度 |
| `lw` | 线宽（折线/曲线类） | `lw=2.0` 更醒目 |
| `s` / `alpha` | 散点大小/透明度（scatter_fit） | 点密时 `alpha=0.5` 减遮挡 |
| `ms` | 标记大小（plot_line） | — |
| `annot_size` | 格内字号（confusion_matrix） | 类别多格小时调小 |
| `band_alpha` / `fill_alpha` | 误差带/雷达填充透明度 | — |

```python
# 答辩场景一键微调：宽屏大图 + 字号放大 + 图例右上
pt.grouped_bar(df, x="dataset", y="accuracy", group="model",
               figsize="slide", font_scale=1.4, legend_loc="upper right")
# 期刊双栏通栏
pt.plot_line(dfc, x="epoch", y="val_accuracy", group="model", figsize="double")
# 聚焦区间 + 加粗主线
pt.plot_line(dfc, x="epoch", y="val_accuracy", group="model",
             ylim=(60, 95), lw=2.0)
```

  工作模式建议：**先用默认参数出"满意初版"（零参数调用即学术规范），有具体不满（图太小/字太小/图例挡线）再用对应参数一行微调**——不必预先调参；

- 中文字体自动兜底（仅追加本机实际存在的字体）、无界面环境安全（Agg）。

### 5.2 手动绘图时（模板覆盖不到的图型）

```python
import matplotlib.pyplot as plt
import matplotlib

plt.style.use(r"<本技能目录>/assets/academic.mplstyle")  # 技能目录见技能加载信息，勿写死绝对路径
# 若本机中文字体缺失，追加：
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# 绘图后保存
fig.savefig(r'.temp\图1_ xxx.png', dpi=300, bbox_inches='tight')
# 期刊投稿另存矢量版：fig.savefig(r'.temp\图1_ xxx.pdf')
```

要点：
- 图表中间产物存 `.temp/`，最终图片单独交付
- 输出 PDF 用 `pdf.fonttype = 42`（TrueType，避免 Type 3 字体被期刊拒收）——样式文件已配置
- 误差线：`ax.bar(..., yerr=err, capsize=3)`；显著性标注用短横线 + 星号手绘（`ax.plot` + `ax.text`）
- 中文图与英文图遵循用户论文语言；中文字体用黑体/宋体，不要用默认字体出现方框
- 数据文件较大时先在 `.temp/` 落盘脚本与数据，避免命令行内联超长代码

## 6. 三线表规范（含生成脚本）

三线表 = 顶线 + 栏目线 + 底线，无竖线。

| 组成 | 线宽 |
|---|---|
| 顶线、底线 | 1.5 pt |
| 栏目线（表头下） | 0.75 pt |

**首选方式：用本技能自带脚本生成**（`tools/three_line_table.py`，依赖 pandas + python-docx）：

```python
import sys
sys.path.insert(0, r"<本技能目录>/tools")
import pandas as pd
from three_line_table import df_to_three_line_table

agg = df.groupby(["dataset", "model"])["accuracy"].agg(["mean", "std"]).reset_index()
df_to_three_line_table(
    agg, caption="表1 各模型的测试准确率",
    note="注：数据为5次独立重复实验的均值±标准差。",
    mean_sd_cols=[("mean", "std")], decimals=2,
    save_path=r".temp\表1.docx")
```

脚本自动处理：顶/底/栏目线线宽（1.5/0.75 pt）、无竖线、**默认全表居中**（高校学位论文规范）、表头居中加粗、**长表跨页表头自动重复**（tblHeader）、表标题置上、表注置下（字号小于正文）、中文字体宋体+西文 Times New Roman。支持 `sig_map` 参数给数值附加显著性星号。

对齐规范两流派（按目标场景选）：

| 场景 | 规范 | 脚本用法 |
|---|---|---|
| 学位论文/课程论文（默认） | 全表居中 | 默认即居中，无需参数 |
| 部分期刊/APA 统计表 | 数字列右对齐（小数点对齐），文字列左对齐 | `align={"准确率": "right", "n": "right", "模型": "left"}` |

内容规范（手工制表时遵循）：
- **学位论文场景全表居中**；期刊投稿按上表切换；同一篇文档内对齐方式保持统一
- 同列有效位数一致；单位统一置于表头"指标（单位）"处，不逐格重复
- 统计学标记：\* p<0.05，\*\* p<0.01，\*\*\* p<0.001，含义写入表注
- 表注置表格下方："注：xxx"，字号小于正文
- 跨页长表：表头须在续页重复（脚本已自动处理）

python-docx 生成三线表要点（手工实现时，脚本已内置同样逻辑）：
```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def set_cell_border(cell, top=None, bottom=None):
    """通过 XML 控制单元格上下边框，实现三线表"""
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for edge, sz in (('top', top), ('bottom', bottom)):
        if sz:
            el = OxmlElement(f'w:{edge}')
            el.set(qn('w:val'), 'single'); el.set(qn('w:sz'), str(sz))
            el.set(qn('w:color'), '000000')
            borders.append(el)
    tcPr.append(borders)
# 首行单元格 top=12 bottom=6；末行单元格 bottom=12；其余无线
```

## 7. 统计分析报告规范与自检清单

### 7.1 报告规范

- 描述统计：均值 ± 标准差（±s）或中位数（四分位距），注明 n
- 检验结果完整报告：统计量 + 自由度 + p 值，如"t(38)=2.41, p=0.021"
- p 值报告实际值（p=0.032）而非仅"p<0.05"；p<0.001 可写区间
- 效应量（Cohen's d、η² 等）按期刊要求补充
- 组间比较方法在图注或表注中注明（如"两组比较采用独立样本 t 检验"）
- 严禁篡改或选择性报告；数据异常（缺失、离群）如实说明处理方式

### 7.2 交付前自检清单（逐项核对）

- [ ] 正态性/方差齐性检验已做且方法选择与之匹配（非正态未用参数检验）
- [ ] 每个统计结论三要素齐全：统计量 + 自由度 + p 值
- [ ] 无"p=0.000"写法（应写 p<0.001）
- [ ] 事后检验注明方法（Tukey/Games-Howell/Dunn），且做了多重比较校正
- [ ] 效应量已报告（t 检验→Cohen's d；ANOVA→η²；相关→r 即效应量）
- [ ] 图表误差线类型（SD/SE/CI）已在图注说明
- [ ] 缺失值与离群值处理方式已如实写入方法部分
- [ ] 示例/演示数据已明确标注，未与真实实验数据混淆
- [ ] 每个图表在正文中被引用和解读

## 8. AutoReport：CSV 一键分析报告

**入口脚本**：`tools/auto_report.py`——把本指南的全部能力串成闭环：

```
CSV → 数据质量检查（第1节清单） → 智能图表推荐（第3节逻辑代码化）
   → 自动出图（第5节模板） → 自动统计检验（第2节决策表）
   → 结果章节文字（第7节报告格式） → Markdown 分析报告
```

**使用方式**：

```bash
# 推荐模式：只出图表推荐与质量检查，不擅自选型（默认，人机协同）
python tools/auto_report.py data.csv

# 全自动模式：按推荐执行全流程（适合已明确分析目标的场景）
python tools/auto_report.py data.csv --yes

# 指定分析目标（推荐用法：先看推荐，再指定）
python tools/auto_report.py data.csv --group dataset --value accuracy --yes   # 组间比较
python tools/auto_report.py data.csv --x train_samples --y accuracy --yes     # 相关分析
```

**三条自动路径**（v1.3）：

| 数据特征 | 自动执行的套装 |
|---|---|
| 类别列 + 数值列（`--group/--value` 或推荐命中） | **组间比较四件套**：分组柱状图 + 小提琴图（含显著性星号）+ Q-Q 图（前提检验可视化）+ 描述统计三线表（docx） |
| 检测到 `y_true + y_score` 二分类预测表（不指定参数直接 `--yes`） | **分类评估三件套**：ROC（多模型 AUC）+ PR 曲线（AP）+ 混淆矩阵（行归一化 + 各类 P/R/F1） |
| 连续×连续（`--x/--y`） | 散点+拟合图 + 自动相关分析（正态性判定决定 Pearson/Spearman 主报） |

**设计边界（必须遵守）**：
- **推荐不是决定**：默认只出建议，由用户或上层智能体确认后再执行；
- **方法自动降级**：正态性不满足自动走非参数路径（如 Kruskal-Wallis），不强行 t 检验；方差不齐自动 Welch；
- **文字只写客观层**：自动生成的结果描述只含统计量与差异方向，科学解释由作者完成；
- **报告脚注声明**：每份报告标注"统计量由真实数据计算，结论解释权归作者"，提醒作者复核。

**智能体协同用法**：加载本技能后，用户说"帮我分析这个 CSV"，智能体可先跑推荐模式展示建议，与用户确认分析目标后用 `--group/--value` 或 `--x/--y` 执行全自动流程，再基于生成的图表与统计结果补充解读文字。

## 9. 图表规范体检（智能体工作流·导师视角诊断）

**这是本技能独有的智能体级能力**：用户把**已经画好的图**（截图/导出图）发进来，智能体用视觉能力对照本指南规范检查。纯 Python 绘图库做不到"看图"，只有多模态智能体平台能实现。

**痛点依据**（真实用户调研，知乎/CSDN 高赞帖）：研究生最痛的不是"没有检查项"，而是**"被导师打回时不知道问题出在哪"**——"图重画，这个风格不像学术图"这种批注背后是一整套没人教的隐性规范。因此体检的输出形态必须是**"导师视角的一句话诊断"**，而不是干巴巴的检查表。

**执行流程**（用户说"帮我检查一下这个图 / 导师让我重画，帮我看看哪里有问题"时）：

1. **接收图片**，用视觉理解能力读取图表内容；
2. **逐项对照检查清单**（下表），每项给出 ✓/✗/⚠ 与具体证据；
3. **先输出一句"导师视角诊断"**（人话，先回答"最可能被骂什么"），再附问题清单；
4. **问题按"被骂概率"排序**：投稿硬伤 > 规范偏离 > 优化建议，每条附修改方案；
5. **严重问题给出重画建议**：说明用哪个模板（第 5 节）+ 数据要求，可直接转出图流程。

**诊断话术模板**（三选一开头）：
- "这张图最可能被批的是 ____（具体到元素）。导师看到它的第一反应大概率是：____（模拟一句批注）。"
- "三个问题按被骂概率排序：①____ ②____ ③____。①不改必返工，②看导师严格程度，③锦上添花。"
- "结论：修改后可用 / 建议重画 / 可直接投稿。理由：____。"

**检查清单**（对照第 4 节通用规范）：

| 检查项 | 判定标准 | 严重度 |
|---|---|---|
| 坐标轴单位 | 物理量含单位且格式规范（"量/(单位)"）；无量纲量不乱标单位 | 硬伤 |
| 误差线 | 组间比较类图必须标注误差线且图注说明类型（SD/SE/CI） | 硬伤 |
| 截断轴/误导 | Y 轴不从 0 开始未声明、双 Y 轴、3D 效果 | 硬伤 |
| 图例完整性 | 每组数据有图例且与图中内容一致 | 硬伤 |
| 配色可辨性 | 黑白打印后组间可辨（颜色+线型/纹理双通道）；色盲友好 | 偏离 |
| 字号可读性 | 刻度/图例/标注 ≥9 pt，缩放后仍可读 | 偏离 |
| 图注规范 | 图注在图下方、格式"图N xxx的xxx结果"、句末无标点 | 偏离 |
| 统计标注 | 显著性星号有定义（* p<0.05 等）；统计量三要素完整 | 偏离 |
| 饼图滥用 | 类别>5 的饼图、占比相近的饼图 | 建议 |
| 过度装饰 | 网格过密、渐变填充、装饰阴影等干扰读图 | 建议 |

**图文一致性扩展检查**（用户同时提供论文正文/图注文字时执行；依据：审稿人拒稿高频原因调研）：

| 检查项 | 怎么查 | 严重度 |
|---|---|---|
| 样本量一致 | 正文/方法写"n=10"，图注与图中数据点是否 n=10 | 硬伤 |
| 结论方向一致 | 正文说"实验组显著升高"，图中实验组是否确实高于对照组（读图验证） | 硬伤 |
| 编号引用对应 | "图3"是否真实存在且是第 3 张；正文引用的每个图表编号在文中都有对应图 | 硬伤 |
| 图注与图内容一致 | 图注说"三组对比"，图中是否三组 | 偏离 |

**话术红线**：体检结论用"修改后可用 / 建议重画 / 可直接投稿"三档给出；发现疑似编造数据（图内数值与常识矛盾、图文方向相反）时按学术诚信红线提示用户核对，**不直接替用户下结论**。

## 10. 机制图/通路图绘制规范

机制图（作用机制/科学假说/信号通路）属概念性图示，与统计图表规则不同。内容设计（假说对应、变量选取、图文对照）见 proposal-nsfc.md 第 5 节；本节管视觉与语义规范。

### 语义约定（必须在图注/图例中声明）

| 元素 | 惯例 |
|---|---|
| 实线箭头 | 已确立/主要路径 |
| 虚线箭头 | 推测/潜在/间接路径 |
| T 形端（⊥） | 抑制 |
| 圆点端（●—） | 促进 |
| 箭头中部 +/− | 正/负效应标注 |

不同学科惯例不一（分子生物学多用 ⊥/●—，社科多用 +/−），同一篇内必须统一并在图注声明。

### 布局与要素

- 因果流从左到右（或从上到下），主路径居中且最粗最实
- 调节变量从侧方入箭（指向箭头中部），中介变量位于主路径链上
- 核心节点 ≤7±2 个；节点名与正文术语完全一致（不做同义改写）
- 反馈回路用弧形箭头并注明

### 图注与交付

- 图注声明语义约定与证据来源：已有文献支撑路径 vs 本研究新假说路径（可用实线/虚线或底色区分）
- 路径可附文献编号（如“[12,15]”）或标注“本研究假说”，与 GRADE 证据分级衔接（literature-review.md 第 9 节）
- 矢量格式优先；黑白打印需线型可区分；导出参数同第 4 节通用规范

### 常见错误

- 箭头语义不明（促进/抑制/调节无区分）
- 缺少图例，或图注未声明约定
- 节点名与正文不一致（同义改写导致读者对不上号）
- 把机制图画成技术路线图（混入步骤/流程内容）

### 实施

- 简单框图：matplotlib（FancyArrowPatch/annotate）或绘图工具绘制后导出
- 复杂通路图：用 diagram-drawing 技能生成源文件再导出图片
- 中英文版本分别核对节点命名与图注一致

## 11. 证据综合图（森林图/漏斗图/剂量-反应曲线）

荟萃分析三件套。绘制前确认方法学前提已完成（literature-review.md）：森林图须先定效应模型与异质性检验；漏斗图须有 ≥10 项研究的合并；剂量-反应曲线须完成样条拟合。**图为方法学结果呈现，不得用绘图掩盖缺失的分析。**

### 森林图（含亚组）

要素清单：
- 每研究一行：点估计方块（大小∝权重）+ 95%CI 横线
- 总效应用菱形（不是方块）；亚组各自给亚组合并菱形 + 交互检验 P 值（literature-review.md 第 12 节纪律）
- 右侧数值列：各研究权重 %、点估计(95%CI)
- 标题区：效应量指标与模型（如“RR (95% CI)，随机效应模型”）；异质性 I² 与 P 值；总样本量
- 无效应线（RR=1 / MD=0）竖直虚线，必须标注刻度含义

matplotlib 骨架（样式用本技能 academic.mplstyle，中间产物存 `.temp/`）：

```python
fig, ax = plt.subplots(figsize=(7, 6))
for i, (est, lo, hi, w) in enumerate(rows):          # rows 自 literature-review.md 第 4 节证据矩阵提取
    ax.plot([lo, hi], [i, i], color='black')          # 95%CI 横线
    ax.scatter(est, i, s=40*w, marker='s', color='black')  # 方块大小∝权重
ax.axvline(1, ls='--', color='gray')                  # 无效应线（RR=1）
ax.scatter(total_est, n+0.5, marker='D', s=80, color='black')  # 总效应菱形
ax.plot([total_lo, total_hi], [n+0.5, n+0.5], color='black')
ax.set_yticks(range(n)); ax.set_yticklabels(labels)   # 研究名（作者+年份）
ax.set_xlabel('RR (95% CI)'); ax.invert_yaxis()       # 首篇研究在顶部
# 图例下方文字块：I²=x%, P_het=y; 总效应 RR=a (b-c)
```

亚组森林图：按亚组块分组排序，组间加空行与分组标题，每组末行加亚组合并菱形，图注报交互作用 P。

### 漏斗图（发表偏倚检测）

要素：
- 横轴效应量（对数尺度更稳定）、纵轴标准误 SE（上大下小，倒漏斗形）
- 散点为各研究；叠加合并效应为中心的 95% 置信扇形（伪 95%CI 区域）
- 不对称时只能提示可能发表偏倚，不能断言；须结合 Egger 检验（连续 ≥10 项研究才可靠，建议报告 P 值）
- 图注写明：纳入研究数、中心线含义、检验结果

```python
ax.scatter(ests, ses, s=25)                        # 各研究
xs = np.linspace(center-1.96*se_max, center+1.96*se_max, 50)
ax.plot(xs, np.abs(xs-center)/1.96, 'k--')         # 右侧置信扇形边界
ax.plot(2*center-xs, np.abs(xs-center)/1.96, 'k--')  # 左侧
ax.set_xlabel('效应量(log尺度)'); ax.set_ylabel('标准误 SE')
ax.invert_yaxis()                                   # SE 大在上，呈倒漏斗
```

### 剂量-反应曲线

- 横轴暴露量（单位必标，如“酒精摄入 g/day”）、纵轴效应量（通常以参照组为 1 的 RR）
- 参照剂量垂直虚线 + RR=1 水平虚线
- 限制性立方样条拟合中位数曲线 + 95%CI 阴影带；P 整体与 P 非线性写入图注
- 数据点（各剂量组合并 RR）可叠加展示，但避免与 CI 带冲突
- 样条拟合用 R `dosresmeta` / Stata `glst`（literature-review.md 第 11 节），Python 端只做呈现

### 通用纪律

- 三图均必须正文中被引用与解读，图注句末无标点（第 4 节规范）
- 数据来源：全部取自 literature-review.md 第 4 节证据矩阵提取结果，不重新手填
- 黑白打印友好：研究点用实心/空心区分亚组
- 多结局/多指标的森林图不合并到一张（避免坐标轴含义混淆）

> AI生成