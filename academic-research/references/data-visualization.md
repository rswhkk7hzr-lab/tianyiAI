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
1. 图表类型选择
2. 学术图表通用规范
3. matplotlib 实施规范
4. 三线表规范
5. 统计分析报告规范

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
| 流程/机制 | 流程图/示意图 | 用 diagram-drawing 相关能力或绘制 |

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

> AI生成