# 多人协作指南 — yangkai258/video-clipper

本文档给两个本地开发者 + Codex 协助用的协作流程。
**目标**:你、你的朋友、Codex 三方都能贡献代码,最终都通过 PR 合入 `yangkai258/video-clipper`。

---

## 0. 整体关系图

```
yangkai258/video-clipper  ←  原作者仓库 (upstream, 只读)
            ▲
            │  PR (Compare & pull request)
   ┌────────┴────────┐
   │   你的 fork    │   朋友 fork
   │  你的账号/      │   朋友账号/
   │ video-clipper   │  video-clipper
   └────────┬────────┘
            │
       本地 clone / Codex 工作区
```

**核心规则**

- 改代码都在自己 fork 下的独立分支做,**不直接动 main**
- 改完 `push` 到自己 fork,然后从 fork 提 PR 给原作者
- 同步原作者的最新进度:`upstream/main` → 你的 `main`

---

## 1. 一次性准备(每人都要做一次)

### 1.1 注册 GitHub + 配置 SSH

如果还没有 SSH key:

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub
```

把输出的公钥粘贴到 **GitHub → Settings → SSH and GPG keys → New SSH key**。

测试连通:

```bash
ssh -T git@github.com
```

看到 `Hi <你的用户名>! You've successfully authenticated...` 就 OK。

### 1.2 Fork 仓库

浏览器打开 https://github.com/yangkai258/video-clipper,点右上角 **Fork**。

完成后你拥有 `https://github.com/<你的账号>/video-clipper`。
你朋友做同样动作,得到他自己的 fork。

### 1.3 Clone 到本地

```bash
# 替换 <你的账号>
git clone git@github.com:<你的账号>/video-clipper.git
cd video-clipper
```

### 1.4 配置 upstream 远程

```bash
git remote add upstream git@github.com:yangkai258/video-clipper.git
git remote -v
```

应该看到:

```
origin    git@github.com:<你的账号>/video-clipper.git    (fetch/push)
upstream  git@github.com:yangkai258/video-clipper.git    (fetch/push)
```

---

## 2. 日常协作流程

### 2.1 开工前:同步 upstream

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

### 2.2 切到新分支干活

分支命名建议:`feat/xxx`、`fix/xxx`、`docs/xxx`、`refactor/xxx`

```bash
git checkout -b feat/your-feature
```

### 2.3 写代码 + 提交

```bash
# 写代码...
git add .
git commit -m "feat: 简短描述你做了什么"
```

### 2.4 推到自己的 fork + 提 PR

```bash
git push -u origin feat/your-feature
```

然后浏览器打开 `https://github.com/<你的账号>/video-clipper`,点 **Compare & pull request** 按钮,
按提示对比 `yangkai258/video-clipper` 的 `main` 分支提 PR。

### 2.5 处理 PR review

原作者 review 后会在 PR 上评论,你按反馈修改后 `git push` 同一分支,PR 自动更新。
PR 合并后,你本地可以删除该分支:

```bash
git checkout main
git branch -d feat/your-feature
git push origin --delete feat/your-feature
```

---

## 3. Codex 协助场景

当你在 IDE 里用 Codex(或其他 coding agent)帮改代码时,沿用上面规则:

- **不要**让 Codex 直接 commit 到 `main` 或 `beta`(主分支)
- 让 Codex 在独立分支工作(比如 `codex/fix-cover-alignment`)
- Codex 改完后,你来 review + commit + push + 提 PR

### 3.1 跟 Codex 协作的典型工作流

1. 你:`@codex 帮我修一下 cover 居中 bug`
2. Codex:在 `codex/xxx` 分支改代码 + 跑测试 + commit
3. 你:看 diff,决定是否采纳
4. 采纳 → 你 push 这个分支 + 提 PR
5. 不采纳 → 你 reset 回 main,告诉 Codex 重新做

### 3.2 让 Codex 自动提 PR(可选)

如果 Codex 环境有 GitHub CLI (`gh`) + 个人 token,可让它:

```bash
gh pr create --base main --head codex/xxx --title "..." --body "..."
```

但要小心:**永远先看 diff,再提 PR**,不要让 agent 自动推送到 main。

---

## 4. 常见问题

### 4.1 提交冲突:upstream/main 跟我的分支差太多

```bash
git fetch upstream
git checkout main
git merge upstream/main  # 同步到最新
git checkout feat/your-feature
git rebase main           # 把你的分支基于最新 main 重放
# 解决冲突...
git push -f origin feat/your-feature
```

### 4.2 我提交到了 main 怎么办

```bash
# 把 commit 移到新分支
git branch feat/oops main
git reset --hard upstream/main
# main 现在回到上游最新,你的 commit 在 feat/oops 上
git push -f origin main   # 强制推送覆盖 main (慎用,需要确认没有 push protection)
```

更安全的做法:直接在 GitHub 上点 **Revert** 按钮撤销误提交。

### 4.3 SSH 密钥泄露

立刻到 GitHub → Settings → SSH and GPG keys 删除该 key,然后生成新 key。

---

## 5. 联系

- 原作者仓库:https://github.com/yangkai258/video-clipper
- 提 issue / 讨论:https://github.com/yangkai258/video-clipper/issues

协作愉快 🎬