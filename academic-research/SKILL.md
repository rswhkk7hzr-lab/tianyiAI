---
name: academic-research
description: 面向大模型微调实验研究的科研全流程技能，以"微调实验科研流水线"为主线组织七大通用科研模块与一个领域方法学层。【领域层】大模型微调实验方法学——以「低资源条件下实验结论稳健性」为研究问题（单 seed 结论可信度/结论翻转率/训练病理与泛化相关性/精度-成本权衡）：实验设计（基线/微调策略对比矩阵/消融原则/多 seed 稳健性协议）、训练曲线确定性诊断（过拟合/欠拟合/Loss spike/振荡/早停/发散，含标注图与风险卡片报告，诊断输出可变量化）、**结论稳健性检验（robustness_check：逐 seed 名次翻转图/翻转率/最少稳健 seed 数/配对显著性）**、**病理-泛化相关性分析（pathology_correlate：诊断输出变量化+分组检验）**、消融与基线对比三线表（最优加粗/Δ提升/组件开关/指标对比图）、多 seed 评估与数据泄漏红线。【流程层·七模块】(1) 文献综述生成——结构设计、批判性综述、PRISMA 2020、GRADE 证据分级、荟萃分析、自动检索 API；(2) 数据分析可视化——数据质量检查、统计方法决策表、十二类学术图表模板、三线表、CSV 一键分析报告（AutoReport）、机制图/森林图、导师视角图表诊断；(3) 参考文献排版——GB/T 7714-2015 国标著录、批量格式化、三级引用核验、Crossref 真伪核验与元数据补全、年份结构分析；(4) 论文与文章润色——文体识别、语言学术化、概念修正、多语言与英文学术写作；(5) 申报书撰写——NSFC 核心章节、科学假说图、评审人视角毙稿风险体检；(6) 学术文档导出——Word/PDF 排版组装、图表嵌入、交付检查；(7) 审稿 rubric——投稿前多维度自审与审稿意见撰写。当用户需要大模型微调实验（LoRA/QLoRA/Full-FT 对比、训练曲线诊断、消融实验、微调论文写作），或撰写文献综述/系统综述、生成论文图表/三线表/机制图/森林图、整理或核验参考文献、润色或中英转换论文、撰写申报书或毙稿体检、导出 Word/PDF 文档、投稿前自审时使用。
name_cn: 微调实验科研流水线
description_cn: 以「低资源条件下微调实验结论稳健性」为研究问题的大模型微调实验方法学（多 seed 稳健性/训练诊断/消融对比/病理-泛化相关性）＋文献综述、数据可视化、参考文献核验、论文润色、申报书、文档导出、审稿自审七大通用模块一站式辅助。
create_source: super-agent-skill-creator
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'f7d8c40d-6a7f-4436-b876-75aafc791c7d'
  PropagateID: 'f7d8c40d-6a7f-4436-b876-75aafc791c7d'
  ReservedCode1: 'fd38291b-aa23-482b-922d-c13fbe9000b3'
  ReservedCode2: 'fd38291b-aa23-482b-922d-c13fbe9000b3'
---

# 微调实验科研流水线

面向**大模型微调实验研究**的科研全流程辅助，演示课题为「低资源条件下微调实验结论的稳健性研究——以电信告警分类为例」（研究问题框架见领域层）。技能不是七个并列工具，而是**一条科研流水线**：从选题综述到投稿自审，每个科研阶段有对应模块与工具，前一阶段的产出物是后一阶段的输入。

## 科研流水线全景

```
①选题综述 → ②实验设计 → ③训练监控 → ④结果分析 → ⑤论文写作 → ⑥投稿自审 → ⑦成果交付
  模块一      领域层§2    train_doctor  模块二+     模块四       模块三      模块六
                         +领域层§3   auto_report              +模块七
                         实验表格     experiment_table
```

复合任务（如"帮我跑完这组微调实验并写成论文"）按流水线阶段依次加载所需模块，不要一次性加载全部；每个模块产出规范化中间产物（图/表/报告）供下一阶段直接引用。

## 领域层：大模型微调实验方法学（本技能领域纵深）

- **研究问题**：低资源条件下微调实验结论的稳健性——**RQ1** 单 seed 结论可信度与结论翻转率；**RQ2** 训练病理模式与泛化性能相关性（train_doctor 诊断输出变量化）；**RQ3** 显存/延迟预算下的精度-成本权衡；载体任务为电信告警工单分类微调（基座 vs Full-FT/LoRA/QLoRA/Prefix-Tuning）
- **路由关键词**：大模型微调、fine-tuning、LoRA、QLoRA、Prefix-Tuning、全参微调、训练曲线诊断、过拟合、欠拟合、loss spike、学习率、早停、训练发散、消融实验、消融表、基线对比、对比实验表、多seed、随机种子、稳健性、可复现性、实验设计、微调论文、训练日志分析
- **指南**：`references/llm-finetune-experiment.md`（七节：研究问题/实验设计规范/训练诊断/评估规范/实验表格/演示数据/流水线衔接）
- **工具**：
  - `tools/train_doctor.py` —— 训练曲线确定性诊断：过拟合/欠拟合/未收敛/Loss spike/振荡/发散/早停建议/eval 倒置/指标背离/调度建议；输出标注诊断图+风险卡片报告+`.diagnosis.json` 复现存档；`--demo` 四种典型病理自验
  - `tools/experiment_table.py` —— 实验对比表/消融表 → Word 三线表：mean±std 自动合并、每列最优自动加粗（指标方向按名推断可覆盖）、`--baseline`+`--delta` 出 Δ 提升量列、组件开关列自动 ✓/✗、配套指标对比图（嵌入 docx/md）；`--demo` 双表自验
  - `tools/robustness_check.py` —— **结论稳健性检验器（RQ1）**：逐 seed 名次 bump 图（交叉即翻转）、结论翻转率量化、最少稳健 seed 数（子集共识率曲线）、冠亚军配对显著性；判定卡片（稳健/边际/脆弱）+`.robustness.json` 指纹；`--demo` 两任务对照自验
  - `tools/pathology_correlate.py` —— **病理×泛化相关性分析器（RQ2）**：批量调用 train_doctor 把诊断标签变量化，与最终指标合并做分组统计/Spearman/非参数检验；分组对比图+`.correlation.json` 指纹；`--demo` 18 run 样例自验
- **演示数据**：`samples/demo_finetune_results.csv`、`demo_ablation.csv`、`demo_trainlog_{healthy,overfit,lr_high,spike}.csv`、`demo_trainlog_multi_run.csv`+`demo_run_results.csv`（18 run 病理×性能）、`demo_group_comparison.csv`（4任务×3策略×5seed 稳健性矩阵）（人工构造，虚构标注）

## 通用科研模块（按流水线阶段组织）

### ①选题综述 · 模块一：文献综述生成

- **定位**：综述结构设计、批判性综述写作；系统综述方法学（PRISMA 2020、GRADE 证据分级、证据矩阵、荟萃分析）
- **路由关键词**：文献综述、研究现状、综述结构、literature review、系统综述、PRISMA、荟萃/meta 分析、检索策略、纳排标准、质量评价、偏倚风险、GRADE、证据分级、证据矩阵、剂量-反应、干预证据、效应量、特殊人群、亚组分析、自动检索、文献 API、文献数据库检索
- **指南**：`references/literature-review.md`（14 节，含证据综合方法学与自动检索实现）

### ④结果分析 · 模块二：数据分析可视化

- **定位**：原始数据进来 → 规范学术图表 / Word 三线表 / 一键分析报告出去；另覆盖概念性图示（机制图/通路图）与证据综合图（森林图/漏斗图）；图表画完后提供导师视角诊断与图文一致性体检
- **路由关键词**：论文图表、数据可视化、画图、三线表、统计分析、误差线、箱线图、散点拟合、相关热力图、训练曲线、折线图、分析报告、一键分析、ROC、AUC、混淆矩阵、PR曲线、小提琴图、雷达图、Q-Q、正态性、图规范、检查图表、通路图、机制示意图、森林图、漏斗图、剂量-反应曲线
- **指南**：`references/data-visualization.md`（十一节，含模板规范与体检工作流）
- **工具**：
  - `tools/plot_templates.py` —— 十二类绘图模板 + 绘图配方存档 + 返修批量重绘（`--recipe`）
  - `tools/auto_report.py` —— CSV 一键统计分析报告（`--html` 出可视化报告）
  - `tools/three_line_table.py` —— Word 三线表生成（支持最优值加粗 `bold_if`）
- **演示数据**：`samples/` 内 CSV 数据集 + `assets/academic.mplstyle` 学术图表样式

### ⑥投稿自审 · 模块三：参考文献排版

- **定位**：混乱引文进来 → GB/T 7714 国标著录 + 三级引用核验（L1 存在性/L2 元数据/L3 支持性）+ 年份结构报告出去；L1/L2 已由 Crossref 工具自动化
- **路由关键词**：参考文献格式、引用著录、GB/T 7714、文末文献表、引文整理、文献表批量处理、引文体检、文献真伪、核验、引用核验、文献真实性、核验文献、元数据补全、补 DOI、文献年份结构
- **指南**：`references/citation-gbt7714.md`（七节，含格式规范与三级核验工作流）
- **工具**：
  - `tools/citation_formatter.py` —— 批量国标格式化（零参数 = 顺序编码制满意初版）
  - `tools/citation_verifier.py` —— Crossref 真伪核验 + 元数据补全 + 年份结构分析（`--year-report`）
- **演示数据**：`samples/demo_citations_mixed.txt`（真实+编造混合 20 条）

### ⑤论文写作 · 模块四：论文与文章润色

- **定位**：文体识别（学术/文学/实用/混合）→ 按文体分场景处理；学术文稿做语言学术化、概念修正（术语/事实性错误检查）、逻辑与结构优化、多语言与英文学术写作；一般文章优化文笔并匹配文风（华丽/幽默/简洁），保留主题、事实与作者声音
- **路由关键词**：论文或文章润色、改写、语言优化、逻辑优化、文学文笔、华丽文风、幽默文风、摘要、题目、降重改写、概念纠错、术语纠错、概念混淆、多语言、英文写作、中英转换、翻译性改写、术语双语
- **指南**：`references/paper-polish.md`（+ 按文体子指南 `paper-polish-*.md`）

### ⑤论文写作 · 模块五：申报书撰写

- **定位**：撰写线 + 体检线双线系统——国自然 NSFC（面上/青年/地区）核心章节撰写方法、科学假说图/机制图，以及评审人视角毙稿风险体检（主线一致性 / 参考文献年份结构 / 技术路线图）
- **路由关键词**：申报书、立项依据、研究内容、技术路线、标书、NSFC、机制图、科学假说图、申报书体检、毙稿风险
- **指南**：`references/proposal-nsfc.md`（撰写五步 + 体检三件套，双线 10 节）
- **工具**：
  - `tools/citation_verifier.py --year-report` —— 申报书参考文献体检（真伪 + 近5年占比 + 数量评估）
  - `tools/plot_templates.py` —— 技术路线图生成
- **演示数据**：`samples/demo_proposal_draft.md`（虚构标注，内置典型问题供体检演示）

### ⑦成果交付 · 模块六：学术文档导出

- **定位**：Word/PDF 排版组装、图表嵌入、字体页边距规范、交付前导出检查
- **路由关键词**：Word 导出、PDF 导出、文档交付、排版、字体、页边距、图表嵌入、导出检查
- **指南**：`references/document-export.md`

### ⑥投稿自审 · 模块七：审稿 rubric

- **定位**：投稿前多维度自审与审稿意见撰写
- **路由关键词**：审稿、投稿前自审、模拟审稿、审稿意见、拒稿原因、稿件评审、rubric
- **指南**：`references/peer-review.md`

## 通用工作流程

1. **明确需求**：确认任务处于流水线哪个阶段、学科领域、文档类型（期刊论文 / 学位论文 / 申报书 / 课程作业）与交付格式。信息不足时先询问。
2. **加载模块**：按上方路由读取对应 `references/` 文件后再动手。
3. **执行任务**：遵循模块内的规范与模板。
4. **交付前核验**：凡含参考文献的成果，按 `references/citation-gbt7714.md` 第 7.4 节执行三级引用核验（L1/L2 用 `citation_verifier.py` 一键自动化）并随附核验报告；润色类成果按 `references/paper-polish.md` 完成概念检查并输出概念问题清单；微调实验类成果按 `references/llm-finetune-experiment.md` 核对实验设计矩阵与多 seed 口径。
5. **交付成果**：正式文档默认交付 `.docx`（排版与导出规范见 `references/document-export.md`，可用 docx skill 生成）；中间草稿放 `.temp/`。学术图表优先调用 `tools/plot_templates.py` 出图（十二类模板+矢量输出+绘图配方存档+风格预设+返修批量重绘 `--recipe`）；论文三线表用 `tools/three_line_table.py` 生成；"帮我分析这个 CSV" 类需求优先用 `tools/auto_report.py`（先推荐模式确认，再全自动执行，`--html` 出可视化报告）；训练日志诊断用 `tools/train_doctor.py`（零参数自动识别列，`--html` 出体检报告）；多 seed 结果稳健性检验用 `tools/robustness_check.py`（翻转率+最少seed数+bump图）；病理与最终指标相关分析用 `tools/pathology_correlate.py`（诊断变量化+非参数检验）；实验对比/消融表用 `tools/experiment_table.py`（最优加粗+Δ列+✓/✗开关+指标图）；参考文献批量整理用 `tools/citation_formatter.py`（零参数=国标顺序编码制）；文献真伪核验与元数据补全用 `tools/citation_verifier.py`（Crossref 权威源，未命中≠编造）；文献年份结构分析用 `tools/citation_verifier.py --year-report`；Markdown 报告转可视化 HTML 用 `tools/report_html.py`；用户发来已画好的图要求检查时，按 data-visualization.md 第 9 节执行导师视角图表诊断；用户发来文献表要求检查时，按 citation-gbt7714.md 第 7 节执行引文体检/核验；用户发来申报书草稿要求把关时，按 proposal-nsfc.md 体检线执行毙稿风险体检；用户发来训练日志要求分析时，按 llm-finetune-experiment.md 第 3 节执行曲线诊断；投稿前可按 `references/peer-review.md` 自审 rubric 终检；`samples/` 内为演示数据，仅用于功能验证。

**脚本依赖**（用户环境缺失时先安装再调用，不静默降级）：
```bash
pip install matplotlib pandas scipy python-docx
```
其中 scipy 用于统计检验（缺失时绘图可用、检验降级提示）；python-docx 仅三线表/实验表格生成需要。一键自验：`python tools/plot_templates.py --demo`（十二图全通即依赖就绪）；`python tools/citation_formatter.py --demo`（引文解析就绪）；`python tools/citation_verifier.py --demo`（联网核验就绪）；`python tools/train_doctor.py --demo`（训练诊断就绪）；`python tools/experiment_table.py --demo`（实验表格就绪）；`python tools/robustness_check.py --demo`（稳健性检验就绪）；`python tools/pathology_correlate.py --demo`（相关性分析就绪）。

## 学术诚信红线（必须遵守）

- **不编造文献**：参考文献只能来自用户提供的清单或真实检索结果。任何情况下不得凭记忆生成文献条目；缺少文献时明确告知用户并提供替代方案。
- **不编造数据**：不虚构实验数据、统计结果、p 值。示例数据必须明确标注"示例/演示数据"（`samples/` 已全部内置标注）。
- **不虚构实验**：微调实验数据须来自用户真实训练日志或明确标注的构造数据；诊断结论只出证据与建议，训练决策权归研究者。
- **申报书不虚构**：研究基础、前期成果只陈述用户提供的真实材料；体检只输出风险与建议，判断权归作者；不提供规避审查的建议。
- **正当润色**：只做语言与结构优化，不改变作者观点和数据结论；概念/事实性错误属客观错误——标记并给出证据，经用户确认后修正；降重请求仅提供正当的表述改写指导，不协助抄袭规避。
- **代写声明**：为论文、学位论文提供代写性质的内容生成时，输出仅作为写作参考/示范，需向用户说明应由作者本人完成实质性研究与写作。

## 通用写作规范要点

- 术语全文一致（同一概念不要混用多种称谓）。
- 数字与单位符合 GB/T 8170 有效数字规则；单位用国际符号，数字与单位间加空格。
- 图表编号连续（图1、表1），正文必须交叉引用。
- 中文标点用全角，英文语境用半角，不混用。
