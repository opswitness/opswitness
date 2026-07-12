# Paperclip 永久安装清单（P2 第 8 步 — 待批准，尚未执行）

目标机器：用户 MacBook（darwin）。当前沙箱实例（`/private/tmp/.../pp-sandbox`）在验证结束后废弃。

## 安装步骤（每步可单独回滚）

1. **前置检查**
   - `node --version` ≥ 20（已确认 v24.14.1）；端口 3100 空闲；确认沙箱实例已停。
2. **Onboard（真 HOME）**
   - `npx -y paperclipai onboard --yes` → 创建 `~/.paperclip/instances/default/`。
3. **数据库决策（用户已定：外部 Postgres）**
   - 首选：`DATABASE_URL=postgresql://…@127.0.0.1:5432/paperclip`（用户自有 Postgres，绕开
     embedded-PG 的 #8023 崩溃面 + 符合"直接上 Postgres"决策）。
   - 备选：保留 embedded（零运维），接受 `~/.paperclip/instances/default/db/` 为数据目录。
4. **关闭遥测**：`paperclipai configure`（`telemetry.enabled=false` — 沙箱实测默认为 true）。
5. **备份确认**：内置逻辑备份默认 60min/保留 30d（沙箱实测存在）；**注意官方文档明示备份不含
   本地上传与加密主钥** — 把 `~/.paperclip/instances/default/secrets/` 纳入用户现有备份策略。
6. **单实例纪律**：只允许一个 `paperclipai run`（沙箱实测第二实例会静默绑 :3101 共用同一 DB，
   造成调度重复）。用 launchd 服务（onboard 提供或手写 plist）作为唯一启动路径，禁止手动再起。
7. **建 fleet 公司 + API key**
   - `paperclipai company create`（名称如 `fleet`）；`paperclipai token agent` 为 Quarterdeck
     发 scoped agent key → 存 `~/.config/quarterdeck/secrets.yaml`（chmod 600），
     环境变量名 `PAPERCLIP_API_KEY`；`QD_PAPERCLIP__COMPANY_ID` 写入 qd 配置。
8. **活库集成验收（qd 侧，装完即跑）**
   - `qd wrap --job pilot-echo -- sh -c 'echo ok'` → `qd project` → Paperclip UI 里 issue
     `[qd] pilot-echo` 出现两条合法 metadata 的 comment；
   - 断线重放：停 Paperclip → wrap 两次 → 起 Paperclip → `qd project` → 全部补投、顺序正确；
   - 丢 ack 和解：手工删最后一条 `projection_ack` 行 → `qd project` → `reconciled=1`、零重发。
9. **24–48h 试点**：接一个非关键任务（候选：`register-trigger`，只读 EDGAR、6h 间隔），
   `qd adopt launchd com.tianyuzhou.register-trigger`（先 dry-run 审 diff → `--apply` → 手动
   `launchctl unload/load`）。观察 `qd status` + watchdog。
10. **7 天 soak**：接 `feed-monitor`（25min 高频）+ `sox-monitor`（6h）。soak 通过标准：
    零丢 run、零 torn 未愈合、projection 积压归零、watchdog 无假阳性/假阴性。

## 回滚路径

- plist：`qd adopt launchd <label> --rollback`（字节级还原 `.qd-bak`）+ `launchctl load`。
- Paperclip：停 launchd 服务 → `~/.paperclip` 整目录移除（先导出备份）。
- Quarterdeck 账本独立于 Paperclip，回滚后本地审计记录完整保留。

## 已知风险登记

- #8023（不洁退出 crash-loop）：v2026.707 两场景未复现，外部 Postgres 进一步降险；仍保留观察。
- 孤儿子进程不回收（我们的新发现）：wrap 的进程树信号回收可兜底自家任务；上游 bug 报告在任务清单。
- calendar 型任务（conviction-funnel/tci-screen）watchdog 暂不支持（fail-closed 呈现），
  接入前补 croniter。
