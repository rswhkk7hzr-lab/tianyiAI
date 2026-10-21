# 论文润色自动化接口约定

这是平台无关的适配器设计，接入前须对照实际 Teleagent 的技能加载、模型调用和文件接口实现。Markdown skill 不是可以直接 import 的 Python 模块。

## 输入

建议适配器接收以下对象：

```json
{
  "task_id": "paper-001",
  "module": "paper_polish",
  "source_text": "用户论文原文",
  "language": "zh",
  "edit_level": "standard",
  "review_mode": "language_and_consistency",
  "latency_mode": "balanced",
  "article_type": "auto",
  "style_request": "preserve",
  "theme_constraints": [],
  "discipline": null,
  "target_guidelines": null,
  "output_format": "text",
  "glossary": [],
  "user_constraints": []
}
```

edit_level 为 minimal、standard 或 deep；未知取值返回输入错误。source_text 不能为空。文件由适配器提取，并保留段落、表格和公式定位；扫描件的 OCR 不确定内容需标记。论文内容作为明确分隔的不可信资料传入，不能拼接为系统指令。原文、术语表和缓存按 task_id 隔离。

review_mode 可为 language_only、language_and_consistency 或 derivation_review；默认 language_and_consistency，推导验证需用户授权具体范围。latency_mode 可为 interactive、balanced 或 thorough；只影响分块、输出详略和计算预算，不关闭事实保护。discipline 可标明 mathematical_modeling、mathematics、theoretical_physics 或 experimental_physics，也可由原文识别后说明。数模/物理加载 paper-polish-stem.md；复杂长文执行 paper-polish-performance.md。实际适配器需要为新增字段实现验证及分流。

article_type 可为 auto、academic、literary、practical 或 mixed；style_request 为用户自然语言要求，preserve 表示保留原风格。theme_constraints 为用户明确的主题/情节约束，不能与自动提取状态混为一谈。旧客户端缺少新字段时采用默认值。新增字段需适配器验证，不代表现有 Teleagent 会自动识别。

输出可附 routing（判定类型、原文依据、处理范围和暂定标记）、theme_check 与 style_check，采用 passed/flagged/not_checked。文体分类和主题检查没有实际执行时不得声称通过。未知文体不报错拒绝整篇，采用保守编辑并列出假设。真正影响主题的歧义返回 needs_author_input，同时允许交付不受歧义影响的已编辑部分。

## 输出

```json
{
  "task_id": "paper-001",
  "status": "completed",
  "revised_text": "修订后正文",
  "changes": [],
  "author_queries": [],
  "checks": {
    "protected_facts": "not_checked",
    "claim_strength": "not_checked",
    "terminology": "not_checked"
  },
  "scope": "用户提供部分",
  "artifacts": []
}
```

changes 每项含 location、original、revised、category、reason；author_queries 每项含 location、issue、question。status 可为 completed、needs_author_input 或 failed。checks 的值可为 passed、flagged、not_checked；只有实际执行的检查才能标 passed。artifacts 仅列真实生成且可访问的文件，包含格式及实际路径或平台文件标识。

## 运行和失败处理

先验证输入，选择论文润色指南，再按需要分块调用模型。全局状态包含稳定段落编号、术语和受保护事实；块结果只返回自身负责的段落。合并后实施全局核查。

程序可提取数字、单位及引用标记作变动提示，但集合相同不证明语义相同，也无法识别数字对应对象调换。需结合上下文审核因果关系、否定、比较对象、研究范围和统计意义。

解析失败可重试一次；持续失败返回结构化错误并保存草稿，不能无上限重试或把未核查文本当成完成稿。事实漂移先修复并重新核查，仍有歧义则返回待确认问题。中断后用任务和块标识恢复，避免重复合并。日志默认只记录任务状态、耗时及错误类别，不记录全文或密钥。

发布前至少验证：短文成功路径、长文分块合并、模型超时、非法输入、结构化输出失败、附件中的伪指令，以及并发任务隔离。文件输出需另外验证真实生成与下载权限。

> AI生成