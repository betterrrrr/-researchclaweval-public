# Codex `reconnecting` 与 `systemd --user` Docker 权限问题记录

## 1. 现象

### 1.1 `reconnecting`

Codex 在执行任务时反复停在 `reconnecting`，任务不退出或长时间无进展。

### 1.2 `docker` 组权限失败

通过 `systemd --user` 启动的任务，明明当前用户已经加入 `docker` 组，但子进程里仍然访问不了 `/var/run/docker.sock`，表现为：

```text
permission denied while trying to connect to the docker API
```

## 2. 根因

### 2.1 `reconnecting` 的根因

Codex 读取了用户 `~/.codex/config.toml` 里的 `mcp_servers.context7` 配置，后台启动了 `npm exec @upstash/context7-mcp`。
这个 MCP 进程会造成额外的子进程挂起和重连行为，最终把 `codex exec` 卡在 `reconnecting`。

### 2.2 `docker` 组权限失败的根因

`systemd --user` 的 user manager 是旧会话里启动的，它启动时还没拿到新的 supplementary groups。

结果就是：

- 当前 shell 有 `docker` 组
- 但旧的 `systemd --user` 进程没有 `docker` 组
- 它启动的 service 也就继承不到 `docker` 组

## 3. 解决方案

### 3.1 修复 `reconnecting`

在 `run_codex_loops.py` 中为每次运行创建隔离的 `CODEX_HOME`，并清理掉 `config.toml` 里的 `mcp_servers.context7` 配置。

效果：

- 不再自动拉起 `context7-mcp`
- `codex exec` 能正常退出
- 任务输出不再被 `reconnecting` 卡住

### 3.2 修复 `docker` 组权限

重启 `systemd --user` 用户管理器，让它重新加载当前用户的组信息。

可用做法：

```bash
sudo systemctl restart user@<UID>.service
```

重启后验证：

```bash
pgrep -u "$USER" -x systemd | head -n 1 | xargs -I{} sh -c 'grep "^Groups:" /proc/{}/status'
```

应能看到 `docker` 组的 GID。

## 4. 额外注意

- 不要用 `--continue-on-failure` 和 `--no-stop-on-block` 跑 6/7 这种顺序任务，否则 6 失败后会继续跑 7。
- 如果必须临时运行，而 `systemd --user` 还没刷新组权限，可以在命令里包一层 `sg docker -c '...'`。
- `context7` 问题和 `docker` 组问题是两个独立问题，不能混为一谈。

## 5. 最终结论

- `reconnecting`：由 `context7-mcp` 引起，已通过隔离 `CODEX_HOME` 和移除 `context7` 配置解决。
- `docker` 组失败：由旧的 `systemd --user` 未刷新组信息引起，已通过重启 `user@<UID>.service` 修复。
