# Paperclip 永久安装清单 v2（P2 第 8 步 — 待批准，尚未执行）

目标机器：用户 MacBook（darwin）。v1 的五处缺陷已按复核修正：固定版本与绝对 binary、
env 先于 onboard、准确 CLI 形态、完整实例备份、隔离账本故障注入（不再手删 append-only 账本）。

## 前置条件（全部满足才开始）

- [ ] 清理沙箱：`kill <embedded-postgres pid>`（当前 36302 仍在跑）+ 删除
      `…/scratchpad/pp-sandbox`；确认 3100/3101 无监听。
- [ ] **外部 PostgreSQL 就绪**（用户决策；当前 5432 无监听，需先建）：
  ```bash
  brew install postgresql@17 && brew services start postgresql@17
  createdb paperclip
  psql -d paperclip -c "CREATE ROLE paperclip LOGIN PASSWORD '<generated>';
    GRANT ALL ON DATABASE paperclip TO paperclip;
    ALTER DATABASE paperclip OWNER TO paperclip;"
  psql "postgresql://paperclip:<pw>@127.0.0.1:5432/paperclip" -c "SELECT 1;"  # 连接测试
  ```
  （零运维备选：跳过本节用 embedded，接受 #8023 残余风险——非默认。）
- [ ] Node ≥ 20（已确认 v24.14.1）。

## 安装步骤

1. **固定版本全局安装**（launchd 需要稳定绝对路径，npx 一次性运行不提供）：
   ```bash
   npm install -g paperclipai@2026.707.0
   PAPERCLIP_BIN="$(npm prefix -g)/bin/paperclipai"; "$PAPERCLIP_BIN" --version  # 必须输出 2026.707.0
   ```
2. **env 先行，再 onboard**（顺序关键：`DATABASE_URL` 不先设会初始化 embedded PG；
   telemetry 须在第一条命令前禁用，官方推荐环境变量方式，当前版本 `configure` 无 telemetry 段）：
   ```bash
   export PAPERCLIP_TELEMETRY_DISABLED=1
   export DATABASE_URL="postgresql://paperclip:<pw>@127.0.0.1:5432/paperclip"
   "$PAPERCLIP_BIN" onboard --yes     # 注意：onboard 会立即启动服务器（临时前台）
   ```
   把两个 env 同时写进后续 launchd plist 的 `EnvironmentVariables`。
3. **建公司 / service agent / API key**（准确形态；执行前以 `--help` 复核当版参数）：
   ```bash
   "$PAPERCLIP_BIN" company create --payload-json '{"name":"fleet"}'          # 记 company-id
   "$PAPERCLIP_BIN" agent create --company-id <cid> --payload-json \
     '{"name":"quarterdeck","kind":"service"}'                                # 记 agent-id
   "$PAPERCLIP_BIN" token agent create --company-id <cid> --agent <agent-id>  # 记 api-key
   ```
4. **写 Quarterdeck 配置**（新配置分层已实现并有测试：env > secrets.yaml > config.yaml > 默认）：
   ```bash
   mkdir -p ~/.config/quarterdeck && chmod 700 ~/.config/quarterdeck
   cat > ~/.config/quarterdeck/config.yaml  <<'EOF'
   paperclip:
     api_base: http://127.0.0.1:3100
     company_id: <cid>
   EOF
   cat > ~/.config/quarterdeck/secrets.yaml <<'EOF'
   paperclip:
     api_key: <api-key>
   EOF
   chmod 600 ~/.config/quarterdeck/secrets.yaml
   ```
5. **三个 launchd 服务**（模板入库 `templates/quant-fleet/launchd/`，绝对路径，现代命令）：
   - `com.tianyuzhou.paperclip` — `"$PAPERCLIP_BIN" run`，`KeepAlive=true`，
     env 含 `DATABASE_URL`/`PAPERCLIP_TELEMETRY_DISABLED`（**全系统唯一实例**，
     沙箱实测双实例会静默共库复制调度）。
   - `com.tianyuzhou.qd-projector` — `qd project`，`StartInterval=300`。
   - `com.tianyuzhou.qd-watchdog` — `qd watchdog --once`，`StartInterval=300`。
   ```bash
   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.tianyuzhou.paperclip.plist   # 装载
   launchctl bootout   gui/$UID/com.tianyuzhou.paperclip                                 # 卸载（回滚用）
   ```
6. **完整实例备份**（官方明示 DB 备份不含本地上传/workspace/master key）：
   - DB：`pg_dump paperclip`（外部 PG 场景，纳入用户现有 pg 备份策略）；
   - 实例文件：`tar -C ~ -cf - .paperclip/instances/default | age -r <key> > pp-instance.tar.age`
     （secrets/master key + storage/uploads 全含，加密存放）；
   - **恢复演练**：在临时 `PAPERCLIP_DATA_DIR` 解开 tar + `psql < dump` 起一个副本实例，
     确认 UI 可见历史数据后销毁。演练通过才算备份成立。

## 活库验收（qd 侧，装完即跑；账本永不手改）

- 正常链路：`qd wrap --job pilot-echo -- sh -c 'echo ok'` → `qd project` →
  UI 中 `[qd] pilot-echo` 出现两条合法 metadata 评论。
- **断线**：`launchctl bootout gui/$UID/com.tianyuzhou.paperclip` → wrap 两次 →
  **Paperclip 停机期间跑一次 `qd project`，确认非零退出码 + pending>0** →
  bootstrap 拉起 → `qd project` → 全部补投、顺序正确（fail-stop 保序）。
- **丢 ack 和解（隔离账本故障注入，不碰真账本）**：
  ```bash
  export QD_LEDGER_DIR=/tmp/qd-faultlab/ledger        # 隔离环境
  qd wrap --job faultlab -- true && qd project        # 正常投影一轮
  mkdir -p /tmp/qd-faultlab2 && python3 - <<'PY'      # 构造"POST 成功但 ack 写失败"的副本账本
  import pathlib, json
  src = pathlib.Path("/tmp/qd-faultlab/ledger"); dst = pathlib.Path("/tmp/qd-faultlab2/ledger"); dst.mkdir(parents=True)
  for f in src.glob("*.jsonl"):
      lines = [l for l in f.read_text().splitlines() if json.loads(l)["kind"] != "projection_ack"]
      (dst / f.name).write_text("\n".join(lines) + "\n")
  PY
  QD_LEDGER_DIR=/tmp/qd-faultlab2/ledger qd project   # 期望 reconciled>0、零重发（UI 无重复评论）
  ```
- watchdog：`launchctl bootout` 停掉一个已接任务 → grace 内收到 missed 告警。

## 试点与 soak

7. **24–48h 试点**：`register-trigger`（只读 EDGAR、6h 间隔、非关键）——
   `qd adopt launchd com.tianyuzhou.register-trigger`（dry-run 审 diff → `--apply` →
   `bootout`+`bootstrap` 重载）。观察 `qd status` 与 watchdog。
8. **7 天 soak**：接 `feed-monitor`（25min）+ `sox-monitor`（6h）。通过标准：零丢 run、
   零未愈合 torn、projection 积压归零、watchdog 零假阳性/假阴性。

## 回滚路径

- plist：`qd adopt launchd <label> --rollback` + `bootout`/`bootstrap` 重载。
- 服务：三个 launchd 服务逐个 `bootout`；Paperclip 数据在外部 PG + 加密 tar，可整体重建。
- Quarterdeck 账本独立存在，任何回滚不影响本地审计记录。

## 风险登记

- #8023：v2026.707 两场景未复现 + 外部 PG 进一步降险；保留观察。
- 孤儿子进程不回收（我们发现）：wrap 的 killpg 兜底自家任务；上游报告在任务清单。
- calendar 任务（conviction-funnel/tci-screen）watchdog 暂 fail-closed 呈现，接入前补 croniter。
- 步骤 3 的 CLI 参数形态以 `--help` 实测为准（未执行过，Paperclip 无兼容性承诺）。
