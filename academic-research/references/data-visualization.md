---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'c51c5ae1-1be5-4a47-b466-5fc72e7d4267'
  PropagateID: 'c51c5ae1-1be5-4a47-b466-5fc72e7d4267'
  ReservedCode1: 'd4f8d621-fa67-44e9-a739-09fe4aef0a25'
  ReservedCode2: 'd4f8d621-fa67-44e9-a739-09fe4aef0a25'
---

# 数据分析可视化指南

## 目录
1. 图表类型选择
2. 学术图表通用规范
3. matplotlib 实施规范
4. 三线表规范
5. 统计分析报告规范
6. 机制图/通路图绘制规范
7. 证据综合图（森林图/漏斗图/剂量-反应曲线）

## 1. 图表类型选择

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
| 流程/机制 | 流程图/示意图、机制图 | 流程图用 diagram-drawing 能力；机制图按第 6 节规范 |
| 荟萃分析结果 | 森林图、漏斗图、剂量-反应曲线 | 按第 7 节规范；方法学前提见 literature-review.md 第 9-12 节 |

## 2. 学术图表通用规范

- **分辨率**：位图 ≥300 DPI（印刷）；矢量格式（PDF/SVG/EPS）优先于位图
- **尺寸**：单栏图宽约 8 cm（3.15 in），双栏通栏约 17 cm；按目标期刊调整
- **坐标轴**：物理量 + 单位，格式"量符号/(单位)"，如"速度 v/(m·s⁻¹)"；无量纲量只写名称
- **字号**：图内文字（刻度、图例、标注）≥9 pt，成图缩放后仍可读
- **配色**：黑白打印友好（结合线型/填充纹理区分）+ 色盲友好；同组数据同色系
- **图注**：图注置图下方，表注置表上方；格式"图1 xxx的xxx结果"（句末无标点）；多子图用（a）（b）标注
- **正文交叉引用**：每个图表必须在正文中被引用和解读，不能只贴不解

## 3. matplotlib 实施规范

统一使用本技能自带学术样式（位于本技能目录 `assets/academic.mplstyle`）：

```python
import matplotlib.pyplot as plt
import matplotlib

plt.style.use(r'C:\Users\28634\.config\TeleAgent\users\v1_public_2101507457118547968\skills\academic-research\assets\academic.mplstyle')
# 路径按实际技能安装位置调整；若中文字体缺失，追加：
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

## 4. 三线表规范

三线表 = 顶线 + 栏目线 + 底线，无竖线。

| 组成 | 线宽 |
|---|---|
| 顶线、底线 | 1.5 pt |
| 栏目线（表头下） | 0.75 pt |

内容规范：
- 数字列右对齐（或小数点对齐），文字列左对齐，表头居中
- 同列有效位数一致；单位统一置于表头"指标（单位）"处，不逐格重复
- 统计学标记：\* p<0.05，\*\* p<0.01，\*\*\* p<0.001，含义写入表注
- 表注置表格下方："注：xxx"，字号小于正文

python-docx 生成三线表要点（交付 Word 时）：
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

## 5. 统计分析报告规范

- 描述统计：均值 ± 标准差（±s）或中位数（四分位距），注明 n
- 检验结果完整报告：统计量 + 自由度 + p 值，如"t(38)=2.41, p=0.021"
- p 值报告实际值（p=0.032）而非仅"p<0.05"；p<0.001 可写区间
- 效应量（Cohen's d、η² 等）按期刊要求补充
- 组间比较方法在图注或表注中注明（如"两组比较采用独立样本 t 检验"）
- 严禁篡改或选择性报告；数据异常（缺失、离群）如实说明处理方式

## 6. 机制图/通路图绘制规范

机制图（作用机制/科学假说/信号通路）属概念性图示，与统计图表规则不同。内容设计（假说对应、变量选取、图文对照）见 proposal-nsfc.md 第 4 节；本节管视觉与语义规范。

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
- 路径可附文献编号（如"[12,15]"）或标注"本研究假说"，与 GRADE 证据分级衔接（literature-review.md 第 9 节）
- 矢量格式优先；黑白打印需线型可区分；导出参数同第 2 节通用规范

### 常见错误

- 箭头语义不明（促进/抑制/调节无区分）
- 缺少图例，或图注未声明约定
- 节点名与正文不一致（同义改写导致读者对不上号）
- 把机制图画成技术路线图（混入步骤/流程内容）

### 实施

- 简单框图：matplotlib（FancyArrowPatch/annotate）或绘图工具绘制后导出
- 复杂通路图：用 diagram-drawing 技能生成源文件再导出图片
- 中英文版本分别核对节点命名与图注一致

## 7. 证据综合图（森林图/漏斗图/剂量-反应曲线）

荟萃分析三件套。绘制前确认方法学前提已完成（literature-review.md）：森林图须先定效应模型与异质性检验；漏斗图须有 ≥10 项研究的合并；剂量-反应曲线须完成样条拟合。**图为方法学结果呈现，不得用绘图掩盖缺失的分析。**

### 森林图（含亚组）

要素清单：
- 每研究一行：点估计方块（大小∝权重）+ 95%CI 横线
- 总效应用菱形（不是方块）；亚组各自给亚组合并菱形 + 交互检验 P 值（literature-review.md 第 12 节纪律）
- 右侧数值列：各研究权重 %、点估计(95%CI)
- 标题区：效应量指标与模型（如"RR (95% CI)，随机效应模型"）；异质性 I² 与 P 值；总样本量
- 无效应线（RR=1 / MD=0）竖直虚线，必须标注刻度含义

matplotlib 骨架（样式用本技能 academic.mplstyle，中间产物存 `.temp/`）：

```python
fig, ax = plt.subplots(figsize=(7, 6))
for i, (est, lo, hi, w) in enumerate(rows):          # rows 自第 4 节证据矩阵提取
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

- 横轴暴露量（单位必标，如"酒精摄入 g/day"）、纵轴效应量（通常以参照组为 1 的 RR）
- 参照剂量垂直虚线 + RR=1 水平虚线
- 限制性立方样条拟合中位数曲线 + 95%CI 阴影带；P 整体与 P 非线性写入图注
- 数据点（各剂量组合并 RR）可叠加展示，但避免与 CI 带冲突
- 样条拟合用 R `dosresmeta` / Stata `glst`（literature-review.md 第 11 节），Python 端只做呈现

### 通用纪律

- 三图均必须正文中被引用与解读，图注句末无标点（第 2 节规范）
- 数据来源：全部取自第 4 节证据矩阵提取结果，不重新手填
- 黑白打印友好：研究点用实心/空心区分亚组
- 多结局/多指标的森林图不合并到一张（避免坐标轴含义混淆）

> AI生成