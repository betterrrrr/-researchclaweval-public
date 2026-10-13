# 项目版本记录

记录时间：2026-05-15 19:58 (UTC+8)

## 版本总览

| # | 项目 | 远程仓库 | 分支 | Commit (short) | 最新 Tag | Commit 日期 |
|---|------|----------|------|----------------|----------|-------------|
| 1 | AI-Researcher | HKUDS/AI-Researcher | main | `f9a6f84` | — | 2025-10-16 |
| 2 | AI-Scientist-v2 | SakanaAI/AI-Scientist-v2 | main | `05de31b` (本地领先 1) | — | 2026-04-28 |
| 3 | Auto-claude-code-research-in-sleep | wanshuiyin/Auto-claude-code-research-in-sleep | main | `f8cff0a` | v0.4.6 (README) / v0.1.0 (git tag) | 2026-05-14 |
| 4 | AutoResearchClaw | aiming-lab/AutoResearchClaw | main | `84dad0a` | v0.4.0 | 2026-04-23 |
| 5 | DeepScientist | ResearAI/DeepScientist | main | `02f5ac6` | v1.6.0 | 2026-05-13 |
| 6 | dr-claw | OpenLAIR/dr-claw | main | `abd2c37` | v1.1.4 | 2026-05-05 |
| 7 | EvoScientist | EvoScientist/EvoScientist | main | `a4c9c77` | v0.1.0 | 2026-05-13 |

## 详细信息

### 1. AI-Researcher

- Remote: https://github.com/HKUDS/AI-Researcher.git
- Branch: main
- Commit: `f9a6f8480860c193afff600eeffe3defcee8a978`
- Date: 2025-10-16 14:47:34 +0800
- Message: Add files via upload
- Latest Tag: 无
- 同步状态: 与远程一致

### 2. AI-Scientist-v2

- Remote: https://github.com/SakanaAI/AI-Scientist-v2.git
- Branch: main
- Commit: `05de31b7c5f044218e78f43faba323c6048e3bb1`
- Date: 2026-04-28 16:20:40 +0800
- Message: the ai scientist idea generation 已修复，semantic scholar api 未修复
- Latest Tag: 无
- 同步状态: 本地领先远程 1 个提交（本地有未推送的修改提交）
- 远程 HEAD: `96bd516` (2025-12-19, Merge pull request #78 from conglu1997/main)

### 3. Auto-claude-code-research-in-sleep (ARIS)

- Remote: https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git
- Branch: main
- Commit: `f8cff0a1a6c852c337870fe4d5784de362959313`
- Date: 2026-05-14 18:55:31 +0800
- Message: docs: announce ARIS-Code CLI v0.4.6 in main README (EN + CN)
- Latest Tag: v0.1.0 (git tag) / v0.4.6 (README 公告)
- 同步状态: 与远程一致（本次更新拉取 1 个提交）

### 4. AutoResearchClaw

- Remote: https://github.com/aiming-lab/AutoResearchClaw.git
- Branch: main
- Commit: `84dad0a401404739cfcc47851cd1d282b671bb2f`
- Date: 2026-04-23 13:59:26 -0400
- Message: Merge pull request #240 from Maaannnn/feat/volcano
- Latest Tag: v0.4.0
- 同步状态: 与远程一致（本次更新拉取 53 个提交，stash pop 后 `_literature.py` 存在合并冲突已手动解决）

### 5. DeepScientist

- Remote: https://github.com/ResearAI/DeepScientist.git
- Branch: main
- Commit: `02f5ac63a93c7b04eb07dc67c724d4de03b09d1b`
- Date: 2026-05-13 15:06:57 +0000
- Message: fix(daemon): keep copilot waits user gated
- Latest Tag: v1.6.0
- 同步状态: 与远程一致

### 6. dr-claw

- Remote: https://github.com/OpenLAIR/dr-claw.git
- Branch: main
- Commit: `abd2c3781f0194279ccc2408937d3c38c16fce4f`
- Date: 2026-05-05 22:45:39 -0400
- Message: Merge pull request #197 from OpenLAIR/fix-inno-figure-gen-openai-keys
- Latest Tag: v1.1.4
- 同步状态: 与远程一致（本次更新拉取 301 个提交）

### 7. EvoScientist

- Remote: https://github.com/EvoScientist/EvoScientist.git
- Branch: main
- Commit: `a4c9c779c9a758d8f67fff0826025d584c7fe36a`
- Date: 2026-05-13 14:15:39 +0100
- Message: feat: status and elapsed time indicator (#218)
- Latest Tag: v0.1.0
- 同步状态: 与远程一致（本次更新拉取 13 个提交）

## 本次更新记录 (2026-05-15)

| 项目 | 更新前 Commit | 更新后 Commit | 拉取提交数 | 备注 |
|------|--------------|--------------|-----------|------|
| Auto-claude-code-research-in-sleep | `745f856` | `f8cff0a` | 1 | Fast-forward，无冲突 |
| AutoResearchClaw | `01c4df9` | `84dad0a` | 53 | stash pop 后 `_literature.py` 冲突已手动合并（保留上游 abstract 截断 + 本地行数 cap） |
| dr-claw | `e70918b` | `abd2c37` | 301 | Fast-forward，stash pop 无冲突 |
| EvoScientist | `d7c0eec` | `a4c9c77` | 13 | Fast-forward，stash pop 无冲突 |
