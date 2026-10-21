# academic-research · 微调实验科研流水线

> 2026「天翼AI」杯重庆高校人工智能大赛（重邮赛区）· 科研赋能赛道参赛作品
> 基于 TeleAgent 星辰超级智能体平台开发的 Skill 技能包

## 一句话定位

不是又一个"帮你写论文"的通用助手，而是**一条大模型微调实验科研流水线**——
以研究课题「低资源条件下微调实验结论的稳健性研究——以电信告警分类为例」
为领域纵深，覆盖从选题综述、实验设计、训练诊断、结果分析到论文写作、
投稿自审的完整科研闭环。

```
①选题综述 → ②实验设计 → ③训练监控 → ④结果分析 → ⑤论文写作 → ⑥投稿自审 → ⑦成果交付
```

## 研究问题（课题的科研纵深）

| # | 研究问题 | 演示抓手 |
|---|---------|---------|
| **RQ1** | 单 seed 跑出的"LoRA 优于 QLoRA"可信吗？换种子结论会翻转吗？要几个 seed 才稳？ | 多 seed 矩阵 + 结论翻转率 + 显著性检验 |
| **RQ2** | 训练病理（过拟合/spike/振荡）能预测最终泛化性能吗？ | train_doctor 诊断输出变量化 → 相关性分析 |
| **RQ3** | 显存/延迟预算下四种微调策略的精度-成本权衡前沿？ | 对比表（latency/vram）+ Pareto 呈现 |

三个问题指向同一件事：**实验纪律本身就是研究对象**——这正是本技能
"体检/核验"基因在领域内的落点，也是与通用 AI 最深的差异化。

## 凭什么比通用 AI 好（五个硬论据）

| 维度 | 通用 AI（豆包等） | 本技能 |
|---|---|---|
| **输出确定性** | 每次现场生成代码，可能有 bug，结果不可复现 | 模板/规则引擎确定性产出，12 图全量回归，同输入永远同输出 |
| **训练诊断** | 看曲线给印象级判断（"好像有点过拟合"） | 规则引擎检出 9 类病理，每条附 epoch 区间+数值证据+处置建议 |
| **文献真实性** | 会编造"有模有样"的假文献 | Crossref 权威源三级核验，未命中≠编造，证据可点开溯源 |
| **可复现性** | 对话无存档，改数据重来一遍 | `.recipe.json`/`.diagnosis.json` 数据指纹存档，返修一键重出 |
| **数据安全** | 数据上传第三方云 | 全流程本地处理，实验数据不出本机 |

## 功能全景

### 领域层：大模型微调实验方法学
- `train_doctor.py` —— 训练曲线确定性诊断：过拟合/欠拟合/Loss spike/振荡/发散/早停等 9 类病理，标注诊断图+风险卡片报告
- `experiment_table.py` —— 消融/基线对比表一键出 Word 三线表（最优加粗、Δ提升量、✓/✗开关）

### 通用科研七模块
文献综述（PRISMA/GRADE）· 数据可视化（12 类学术图表+AutoReport 一键分析）·
参考文献（GB/T 7714 + Crossref 真伪核验）· 论文润色（文体路由）·
申报书撰写（毙稿体检双线）· 文档导出 · 审稿 rubric 自审

## 快速验证

```bash
python tools/train_doctor.py --demo       # 四种训练病理自动检出
python tools/experiment_table.py --demo   # 对比表+消融表出 Word
python tools/plot_templates.py --demo     # 12 类学术图全量回归
python tools/auto_report.py samples/demo_group_comparison.csv --group model --value accuracy --yes --html
python tools/citation_verifier.py --demo  # Crossref 真实核验（需联网）
```

依赖：`pip install matplotlib pandas scipy python-docx`

## 实测证据（全部真实跑过）

- 训练诊断四病理样例**精确命中且零误报**（健康基线零检出/过拟合高危/spike 双点/振荡中危）
- 引文真伪核验：真实文献 DOI 直查命中（相似度 1.00），编造条目全部"存疑待复核"
- 申报书体检：内置 13 处典型问题**全部检出**（高 9 + 中 2）
- AutoReport：60 行 CSV → 8 产物+HTML 报告，自动选 Kruskal-Wallis

## 迭代档案

14 个版本完整演进记录见 [`academic-research/CHANGELOG.md`](academic-research/CHANGELOG.md)——
痛点调研→功能映射、真实缺陷修复（含"自验路径≠使用路径"教训）、
老师五方向对齐落地过程，全部留档可溯。

## 目录结构

```
academic-research/
├── SKILL.md                    # 技能入口：流水线路由+工作流程+诚信红线
├── CHANGELOG.md                # 11 版本迭代档案
├── references/                 # 15 个方法学指南（含领域层 llm-finetune-experiment.md）
├── tools/                      # 8 个实测脚本
├── samples/                    # 演示数据（稳健性研究场景：多seed矩阵+病理日志，已标注）
└── assets/academic.mplstyle    # 学术图表样式
```

## Roadmap

- 组会纪要整理（官方六场景最后一块，规划中）
- 实验管理器（多 run 配置-结果登记追踪）
- 训练资源估算（显存/耗时预估）

## 诚信声明

- 演示数据全部人工构造并标注"虚构/演示"，不用于任何真实结论
- 不编造文献、不虚构实验数据；诊断与体检只出证据，判断权归研究者
- 全部文档按平台规范附 AIGC 标识

> AI生成
