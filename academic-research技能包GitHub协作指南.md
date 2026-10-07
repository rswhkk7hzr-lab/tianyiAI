---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '4a565a71-aae2-44d1-a9c4-fb5db84e4aa4'
  PropagateID: '4a565a71-aae2-44d1-a9c4-fb5db84e4aa4'
  ReservedCode1: '187c31d1-cf8d-402f-94a7-b7647b51931e'
  ReservedCode2: '187c31d1-cf8d-402f-94a7-b7647b51931e'
---

# 学术科研助手 Skill · GitHub 协作指南

本文档说明如何在 GitHub 上协作修改 `academic-research` 技能包，适用于首次参与者。

---

## 一、技能包是什么

`academic-research.skill` 本质是一个 zip 压缩包，里面是一个技能文件夹：

```
academic-research/
├── SKILL.md                          # 主入口（含任务路由表）
├── assets/
│   └── academic.mplstyle             # matplotlib 学术图表样式
└── references/
    ├── literature-review.md          # 文献综述生成指南
    ├── data-visualization.md          # 数据分析可视化指南
    ├── citation-gbt7714.md            # GB/T 7714 参考文献排版
    ├── paper-polish.md                # 论文润色美化
    └── proposal-nsfc.md              # 国自然申报书撰写
```

- `SKILL.md` 是总入口，只放路由表和通用规范，**改它要谨慎**
- `references/` 下的 5 个 md 文件是各功能的详细指南，**主要在这里改**
- `assets/` 下的样式文件一般不用动

所有文件都是纯文本 Markdown，用记事本、VS Code、Typora 都能编辑。

---

## 二、首次获取技能包

### 方式 A：直接 clone 仓库（推荐）

```bash
git clone https://github.com/rswhkk7hzr-lab/tianyiAI.git
cd tianyiAI/academic-research
```

### 方式 B：下载 .skill 文件后解压

1. 下载 `academic-research.skill`
2. 把后缀 `.skill` 改成 `.zip`
3. 解压得到 `academic-research` 文件夹

---

## 三、修改技能内容

### 1. 编辑指南文件

用任何文本编辑器打开 md 文件直接改。例如想给文献综述模块加一条写作规范：

打开 `references/literature-review.md`，找到对应章节，添加新条目即可。

### 2. 修改要点

- **可以改**：写作规范、句式库、模板、格式细则、新增章节
- **谨慎改**：`SKILL.md` 的路由表（改错会导致功能无法触发）
- **不要改**：`SKILL.md` 顶部的 `---` 包围的 YAML 元数据（`name`、`description` 等字段，改错会破坏技能注册）
- **保持格式**：Markdown 标题层级不要跳级（1 → 1.1 → 1.1.1）

### 3. 本地验证（可选）

如果有 Python 环境，可运行验证脚本检查格式：

```bash
python skills/skill-creator/scripts/quick_validate.py academic-research
```

输出 `Skill is valid!` 即通过。

---

## 四、提交修改到 GitHub

### 1. 提交本地改动

```bash
cd tianyiAI
git add academic-research/
git commit -m "完善文献综述模块：补充批判性写作句式示例"
```

提交信息建议写清楚改了什么，方便对方 review。

### 2. 推送到 GitHub

```bash
git push origin main
```

如果提示需要认证，使用 Personal Access Token（GitHub → Settings → Developer settings → Personal access tokens → 生成带 `repo` 权限的 Token）。

### 3. 通过 Pull Request 协作（推荐）

更规范的协作方式是走 Pull Request，方便对方审查改动后再合并：

```bash
# 创建新分支
git checkout -b feature/improve-literature-review
# 改完文件后
git add academic-research/
git commit -m "完善文献综述模块"
git push origin feature/improve-literature-review
```

然后到 GitHub 网页上点 `Compare & pull request`，填写说明，提交 PR 等对方审核合并。

---

## 五、把改好的版本打包成 .skill

改完并验证通过后，重新打包生成 `.skill` 文件：

```bash
python skills/skill-creator/scripts/package_skill.py academic-research ./dist
```

会在 `dist/` 目录下生成 `academic-research.skill`，可以单独传给没有 GitHub 的用户使用。

---

## 六、安装新版本到 TeleAgent

1. 把新的 `academic-research` 文件夹（或解压后的 `.skill` 内容）复制到技能目录：
   ```
   C:\Users\<你的用户名>\.config\TeleAgent\users\<你的ID>\skills\academic-research\
   ```
2. **覆盖**旧的文件夹
3. **重启 TeleAgent 桌面端**

新版本即刻生效。

---

## 七、协作约定建议

为了让双方改起来不冲突、好追溯，建议：

1. **一个功能一个分支**：比如改文献综述就建 `feature/literature-review` 分支，不要所有改动混在一个分支
2. **提交信息写清楚**：如"补充三线表跨页处理规范"，不要写"更新"
3. **改完先本地验证**：跑 `quick_validate.py` 确认格式没坏
4. **大改动走 PR**：小修小补直接 push main，大改动走 Pull Request 方便 review
5. **保留原始版本备份**：首次拿到技能包后先备份一份原始版本，改坏了能回退

---

## 八、常见问题

**Q：我没有 Python 环境，能改吗？**
能。md 文件用记事本就能改，只是无法跑验证脚本和打包脚本。改完直接 commit 推送即可，对方有环境可以帮你验证打包。

**Q：改完 push 报 403 权限错误？**
确认你有这个仓库的写入权限，且 Token 勾选了 `repo` 权限。如果是别人的仓库，需要先 fork 再改，再发 Pull Request。

**Q：我想加一个全新功能模块怎么办？**
在 `references/` 下新建一个 md 文件，然后在 `SKILL.md` 的路由表里加一行映射，例如：
```
| 某某需求 | 某某模块 | `references/xxx.md` |
```
最后重新验证和打包。

---

有任何问题，直接在 GitHub 上提 Issue 或联系仓库 owner。

> AI生成