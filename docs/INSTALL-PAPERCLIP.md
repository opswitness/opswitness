# Paperclip 永久安装清单 v3（M2，等待单独批准）

目标机器：用户 MacBook。本文是待执行 runbook，不是授权。M1 只提交代码、模板、
诊断和 dry-run；任何 Homebrew/npm 安装、HOME 写入、Postgres 变更、进程停止或
launchd bootstrap 都必须在 M2 获得单独批准后执行。

## 当前只读基线

`qd doctor --json` 已确认：Node 24 可用；三个 launchd 模板合法且不含 secret；
系统 `psql`、`pg_dump`、`age`、`~/.local/bin/qd` 和 5432 Postgres 尚不可用；
3100 当前由一个临时 npx Paperclip Node 实例占用。执行前必须重新核验 PID 的完整
命令行，不能按旧 PID 盲杀。

## M2 变更清单

### 1. 安装用户级二进制

```bash
brew install postgresql@17 age
brew services start postgresql@17

cd /Users/tianyuzhou/trade/quarterdeck
uv build
uv tool install --force dist/quarterdeck-0.0.1-py3-none-any.whl
test -x "$HOME/.local/bin/qd"

npm config set prefix "$HOME/.local/npm"
npm install -g paperclipai@2026.707.0
```

禁止 root-owned global npm、运行时 `npx` 和依赖 launchd PATH。安装后解析并记录：

```bash
NODE_BIN="$(realpath "$(command -v node)")"
PAPERCLIP_JS="$(realpath "$HOME/.local/npm/lib/node_modules/paperclipai/dist/index.js")"
test -x "$NODE_BIN" && test -f "$PAPERCLIP_JS"
```

### 2. 创建外部 Postgres

生成随机数据库密码，创建 `paperclip` role/database，并用 `SELECT 1` 验证。密码只
进入 `secrets.yaml`，不得写入 shell 脚本、plist、README 或命令参数。实际命令以
安装后的 `psql --help` 和本机认证配置为准。

### 3. 创建严格权限配置

```yaml
# ~/.config/quarterdeck/config.yaml（非敏感）
paperclip:
  api_base: http://127.0.0.1:3100
  company_id: <company-id>
services:
  qd_bin: ~/.local/bin/qd
  paperclip_command:
    - <absolute-node-path>
    - <absolute-paperclip-dist-index.js>
  paperclip_home: ~/.local/share/paperclip
  log_dir: ~/Library/Logs/Quarterdeck
backup:
  directory: ~/.local/state/quarterdeck/backups
  age_recipient: <age-public-recipient>
```

```yaml
# ~/.config/quarterdeck/secrets.yaml（敏感）
database_url: postgresql://paperclip:<generated-password>@127.0.0.1:5432/paperclip
paperclip:
  api_key: <service-agent-api-key>
```

目录必须 `0700`，`secrets.yaml` 必须 `0600`。Quarterdeck 会拒绝出现在
`config.yaml` 的 database URL/API key/TG secret，也会拒绝 `secrets.yaml` 中的
非 secret 字段。

### 4. Onboard 与治理对象

先停止并核验临时 npx Paperclip/embedded Postgres，再确保 3100/3101 无监听。
数据库 URL 由 Quarterdeck 在进程内注入，不出现在 shell history：

```bash
qd service exec paperclip --paperclip-mode onboard
```

随后用绝对 Node + `dist/index.js` CLI 创建 fleet company、Quarterdeck service
agent 和 agent token；每条命令执行前用该固定版本 `--help` 核对参数。把 company ID
写入 `config.yaml`、token 写入 `secrets.yaml`，然后再次运行 `qd doctor`。

### 5. 渲染并安装 launchd

先创建日志目录，再把三份模板渲染到隔离目录并 lint：

```bash
mkdir -p ~/Library/Logs/Quarterdeck /tmp/qd-launchd-render
qd service render paperclip --output /tmp/qd-launchd-render/com.quarterdeck.paperclip.plist --write
qd service render projector --output /tmp/qd-launchd-render/com.quarterdeck.projector.plist --write
qd service render watchdog --output /tmp/qd-launchd-render/com.quarterdeck.watchdog.plist --write
plutil -lint /tmp/qd-launchd-render/*.plist
```

人工审阅后再原子复制到 `~/Library/LaunchAgents/`，并依次执行：

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.quarterdeck.paperclip.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.quarterdeck.projector.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.quarterdeck.watchdog.plist
```

Paperclip plist 使用 KeepAlive；projector 每 30 秒、watchdog 每 60 秒运行。plist 只
包含 `QD_CONFIG_DIR`，不包含数据库 URL、API key 或 token。

## 安装后闸门

### Doctor 与灾备

`qd doctor` 必须全绿。先审 dry-run，再创建一次真实加密备份：

```bash
qd backup create
qd backup create --execute
```

在隔离目录、隔离数据库和非生产端口演练恢复：

```bash
qd backup restore <archive.age> --identity <age-key> \
  --target-root /private/tmp/qd-restore-smoke \
  --database-name qd_restore_smoke --paperclip-port 3310
# 审计划后才添加 --execute
```

恢复后用隔离 DB/目录在 3310 启动 Paperclip，确认 UI 可见历史，再销毁副本。未经
这一验证，备份不算成立。

### 活库四连

1. 正常投影：wrap 后 UI 出现 started/finished 两条评论。
2. 停机积压：Paperclip 停机期间 `qd project` 非零且 pending 增长。
3. 恢复重放：按 job commit order 补投，失败 job 不阻塞其他 job。
4. Lost-ack：只在隔离 ledger/test company 构造，验证 reconcile 不重发；真 ledger
   永不删除、改写或过滤事件。

## Canary 与 Soak

1. register-trigger 只读 canary 运行 24–48 小时。
2. 人工审阅 `qd adopt` diff 后才 `--apply`；始终保留 pristine `.qd-bak`。
3. feed-monitor 与 sox-monitor 运行 7 天，覆盖重启、睡眠唤醒、Paperclip/DB 停机、
   任务 SIGTERM、积压恢复、TG digest 和备份恢复。
4. 通过标准：零漏账、零不可解释重复、零假绿、零进程树残留、积压全部恢复。

## 回滚

- `launchctl bootout gui/$UID/<label>` 停止三个 Quarterdeck 服务。
- `qd adopt launchd <label> --rollback` 字节级恢复原任务 plist，再 bootstrap。
- Paperclip 数据从外部 Postgres + age 备份恢复；Quarterdeck ledger 独立保留。
- 不执行 `git reset`、不手改 ledger、不按未经重新核验的 PID 停进程。
