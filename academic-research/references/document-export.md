---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '55c15a17-fbeb-4043-a5b1-39be22239b07'
  PropagateID: '55c15a17-fbeb-4043-a5b1-39be22239b07'
  ReservedCode1: 'a646a6f7-2f2d-414a-b06e-65dad02189c8'
  ReservedCode2: 'a646a6f7-2f2d-414a-b06e-65dad02189c8'
---

# 学术文档 Word/PDF 导出规范

## 目录
1. 导出路径选择
2. Word 学术文档组装规范
3. 图表嵌入与自动编号
4. PDF 导出三路径
5. 交付前检查清单
6. 工具衔接

## 1. 导出路径选择

| 场景 | 交付格式 | 路径 |
|---|---|---|
| 期刊投稿（多数中文期刊） | `.docx` | 本模块组装规范 + docx skill |
| 期刊投稿（要求 PDF） | `.pdf` | 先组装 docx 再转 PDF（保真优先） |
| 学位论文/申报书 | `.docx` | 同上；导师/学院模板优先 |
| 长报告/汇报稿 | `.html` → 可转 PDF | html-generator skill |
| 期刊提供 LaTeX 模板 | `.tex` → PDF | 按模板走 LaTeX，不用本模块 |

规则：用户未指定时默认 `.docx`；需要 PDF 时先出 docx 源再转，保证两个格式内容一致。

## 2. Word 学术文档组装规范

### 页面设置

| 项 | 默认值 | 说明 |
|---|---|---|
| 页边距 | 上下 2.54 cm，左右 3.17 cm | 学位论文常用，期刊按投稿须知 |
| 行距 | 1.5 倍 | 期刊双倍或按须知 |
| 页码 | 底部居中，正文从 1 起 | 摘要/目录可用罗马数字分节 |
| 页眉 | 章名或期刊名（按须知） | 不强加 |

### 字体字号（中文文档默认）

| 元素 | 中文字体 | 西文字体 | 字号 |
|---|---|---|---|
| 正文 | 宋体 | Times New Roman | 小四（12 pt） |
| 各级标题 | 黑体 | Times New Roman 加粗 | 三级依次小三/四号/小四 |
| 图注表注 | 宋体 | Times New Roman | 五号（10.5 pt） |
| 参考文献 | 宋体 | Times New Roman | 五号 |

英文文档：全文 Times New Roman，正文 12 pt，行距双倍（按期刊调整）。

### 样式层级（用 Word 样式而非手动加粗）

- 标题 1 / 标题 2 / 标题 3 → 对应 `1` / `1.1` / `1.1.1`，不跳级（与 paper-polish.md 格式规范一致）
- 用样式生成目录（引用→目录），避免手敲目录与正文脱节
- python-docx 中用 `doc.add_heading(text, level=n)`；中文字体需逐 run 设置 `font.name` + `rFonts` 东亚字体：

```python
from docx.oxml.ns import qn
run.font.name = 'Times New Roman'
run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
```

### 结构完整件

正式学术文档依次包含：题目页（题目/作者/单位/日期）→ 摘要与关键词 → 目录（长文）→ 正文（引言…结论）→ 参考文献 → 附录（PRISMA 流程图、证据矩阵、核验报告等，见 literature-review.md）。

## 3. 图表嵌入与自动编号

- 嵌入顺序：图注在图下方、表注在表上方；图随正文首次引用后就近放置
- 分辨率：矢量（PDF/EPS/SVG 转 EMF）优先；位图 ≥300 DPI（与 data-visualization.md 第 2 节一致）
- 编号连续：图 1、图 2…表 1、表 2…，不按章节重置（除非期刊要求分章编号）
- 交叉引用：Word 中用"引用→交叉引用"插入题注编号，增删图表后全选+F9 更新域；python-docx 生成时直接写死编号并全文检索核对
- 三线表：按 data-visualization.md 第 4 节的边框 XML 方法实现
- 森林图/机制图等先按 data-visualization.md 生成图片文件，再以 `add_picture` 嵌入

## 4. PDF 导出三路径

| 路径 | 适用 | 要点 |
|---|---|---|
| docx → PDF | 默认首选 | Word"另存为 PDF"或 LibreOffice 无头转换 `soffice --headless --convert-to pdf`；先核对字体嵌入（文件→选项→保存→将字体嵌入文件） |
| HTML → PDF | 长报告/网页风 | html-generator 或 pdf skill；适合含样式的汇报稿，不用于期刊投稿 |
| LaTeX → PDF | 期刊有 .tex 模板 | 严格用模板，图表位图转矢量；不与本模块混用 |

转换后必须逐页抽查：图片是否糊/移位、公式是否乱码、页码是否连续、目录页码是否更新。

## 5. 交付前检查清单

- [ ] 字体：中英文分别正确，无默认字体残留（英文 run 未设 Times New Roman 是高发问题）
- [ ] 标题层级 1→1.1→1.1.1 不跳级，目录与正文一致（更新域）
- [ ] 图表：编号连续、正文均有交叉引用、分辨率达标、图注表注位置正确
- [ ] 参考文献：著录格式按 citation-gbt7714.md 校对，正文标注与文献表一一对应
- [ ] 数字与单位：GB/T 8170 有效数字、单位空格（paper-polish.md 第 5 节）
- [ ] PDF 抽查：字体嵌入、图片清晰、页码目录更新
- [ ] 附录齐全：系统综述附 PRISMA 流程图、证据矩阵、核验报告
- [ ] AIGC 水印：txt/md/pdf/docx 等格式会被系统自动注入水印，属预期行为，不修改不删除；用户问起时如实说明

## 6. 工具衔接

- **docx skill**：复杂排版（样式、页眉页脚、表格边框）优先调用
- **pdf skill**：HTML→PDF 或 PDF 后处理（合并、水印、加密）
- **html-generator skill**：HTML 长报告交付
- 数据图表：matplotlib 按 data-visualization.md 第 3 节样式生成，中间产物放 `.temp/`
- 大文档分块写入：超过 15 页的文档分多次写入组装，避免单次超长失败

> AI生成