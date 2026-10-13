# 修复 Codex CLI `codex exec` 403 刷屏 / 不退出问题

## 问题描述

在使用第三方 API 中转站（而非 OpenAI 官方 endpoint）运行 `codex exec` 时，进程完成任务后不会退出，同时 stderr 持续刷屏输出：

```
403 Forbidden: Country, region, or territory not supported
```

## 根因分析

Codex CLI 内部存在一个**后台 OAuth token 刷新机制**，该机制独立于实际的模型 API 调用。即使用户通过 `OPENAI_API_KEY` 环境变量配置了第三方中转站的 API key，Codex CLI 仍然会在后台尝试连接 OpenAI 官方认证服务器来刷新本地保存的 OAuth token。

关键文件位于 `~/.codex/` 目录下：

| 文件 | 作用 |
|------|------|
| `~/.codex/config.toml` | CLI 配置文件（保留，不删除） |
| `~/.codex/auth.json` | 主 OAuth token |
| `~/.codex/auth_b.json` | 备用 OAuth token |
| `~/.codex/auth_c.json` | 备用 OAuth token |

当这些 `auth*.json` 文件存在时，Codex CLI 的后台线程会持续尝试使用其中的 refresh token 向 OpenAI 官方服务器请求新 token。如果所在地区被 OpenAI 限制，这些请求会持续返回 `403 Forbidden`，导致：

1. **stderr 刷屏**：大量 403 错误信息输出。
2. **进程不退出**：后台 token 刷新线程持续运行，阻止 `codex exec` 进程正常终止。

## 修复方法

### 步骤 1：备份 auth 文件

```bash
mkdir -p ~/.codex/auth_backup
cp ~/.codex/auth*.json ~/.codex/auth_backup/
```

### 步骤 2：删除 auth 文件

```bash
rm ~/.codex/auth.json ~/.codex/auth_b.json ~/.codex/auth_c.json
```

### 步骤 3：验证修复

运行一个简单的 `codex exec` 测试：

```bash
codex exec --json -m gpt-5.4 "echo hello"
```

预期行为：
- 不再有 `403 Forbidden` 刷屏。
- `codex exec` 完成任务后正常退出。

## 注意事项

1. **不要删除 `config.toml`**：该文件包含 CLI 基础配置，与 auth 问题无关。
2. **环境变量认证不受影响**：删除 `auth*.json` 后，Codex CLI 仍然可以通过 `OPENAI_API_KEY` 环境变量正常认证第三方中转站。
3. **备份可恢复**：如果需要恢复官方 OAuth 认证，可以从 `~/.codex/auth_backup/` 复制回来。
4. **新服务器无需处理**：新服务器上不会存在这些 auth 文件，只要通过环境变量配置 API key 即可直接使用。

## 适用场景

- 使用第三方 API 中转站（非 OpenAI 官方 endpoint）。
- 所在地区被 OpenAI 官方服务限制。
- `codex exec` 在 `subprocess.run()` 中被调用且需要正常退出。

## 时间线

- **发现时间**：2026-05-15
- **修复验证**：2026-05-15，删除 auth 文件后 `codex exec` 正常运行并产生 JSONL 输出，无 403 刷屏。
