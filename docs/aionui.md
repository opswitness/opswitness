# AionUi 作为 Quarterdeck 控制台

界面策略（研究结论）：**不自研前端**。三层现成界面：

1. **Paperclip Web UI**（http://127.0.0.1:3100）— 舰队 issue（`[qd] <job>`）、run 评论、
   审批队列、成本看板，投影后自动出现，零配置。
2. **AionUi 对话式控制台** — 只挂 Quarterdeck MCP，自然语言查询外部舰队
   ledger、watchdog、artifact 和投影状态，也可通过本地白名单启动完整工作流。
   Paperclip 的审批决策继续只在 Paperclip Web UI 完成。
3. `qd` CLI — 终端兜底，与 MCP 共用同一套函数，永不打架。

## AionUi 配置

用户级工具必须包含 MCP extra：

```bash
uv tool install --force --with mcp /path/to/distribution.whl
```

在 AionUi 的 MCP 设置中加入：

```json
{
  "mcpServers": {
    "quarterdeck": {
      "command": "/Users/<you>/.local/bin/qd",
      "args": ["mcp"]
    }
  }
}
```

Quarterdeck 从权限为 0700/0600 的本机配置目录读取凭据；不要把 key 复制进 AionUi
的 env/SQLite。若只需读工具，`qd_project_now` 和 `qd_workflow_start` 都不应由模型调用。

## 一键启动完整工作流

Quarterdeck 不在 MCP 中开放 shell。先由本机管理员把完整流程的**唯一入口命令**登记
一次；AionUi 之后只传一个固定 workflow id：

```bash
qd workflow register quarterdeck-showcase \
  --title "Quarterdeck end-to-end showcase" \
  --description "wrap -> outage replay -> gate -> artifact -> digest" \
  --cwd /Users/<you>/trade/quarterdeck \
  -- ~/.local/share/uv/tools/quarterdeck/bin/python \
     /Users/<you>/trade/quarterdeck/examples/showcase/run.py
```

登记文件是 `~/.config/quarterdeck/workflows.yaml`（`0600`）。命令必须是绝对 argv，
不能是 shell/env，不能带疑似 credential，AionUi 不能修改它，也不能附加运行时参数。

然后在 AionUi：

1. 建一个专用对话，确认 `quarterdeck` MCP 已启用。
2. 在 **Scheduled Tasks** 新建任务，Frequency 选 **Manual**，Execution mode 选
   **Existing conversation**，目标选上面的专用对话。
3. 固定 Prompt：

   ```text
   Call qd_workflow_start exactly once with workflow_id "quarterdeck-showcase".
   Do not call any other mutating tool. Return the run_id, then call
   qd_workflow_status for that run_id.
   ```

4. 第一次工具确认只选择“始终允许 `quarterdeck` server 的 `qd_workflow_start` 工具”；
   **不要**允许整个 server，也不要开启 YOLO。该授权是 AionUi 会话级的；会话重建后
   第一次运行会重新确认。
5. 此后进入该 Manual Task，点击 **Run now** 即启动。调用立即返回 run id，后台
   supervisor 脱离 AionUi 会话继续运行。

这是启动意图，不是 M3 审批。工具调用中的高风险副作用仍由 Quarterdeck gate →
Paperclip Web UI 审批；流程退出码也只证明 execution，业务完成必须看 artifact
eval/signoff。完整契约见 [ADR-0004](adr/0004-allowlisted-workflow-launch.md)。

## 为什么不把 Paperclip 官方 MCP 直接挂入 AionUi

2026-07-13 对固定版本 `@paperclipai/mcp-server@2026.707.0` 的发布包审计显示，
它实际注册 41 个工具：23 个读工具、17 个写工具，以及一个可调用任意 `/api`
JSON 端点的 `paperclipApiRequest` escape hatch。写面包括 issue 修改、workspace
控制、approval 创建与决策。服务只接受环境变量中的 bearer token，没有只读模式；
当前 Paperclip board/agent token CLI 也没有可配置的 read-only scope。

发布包 README 少列了源码中真实注册的 `paperclipRequestCheckboxConfirmation`；这里的
数量以 `dist/tools.js` 的注册表为准。

因此直接接入会让 AionUi 中的模型获得治理写权限，并破坏“Paperclip Web UI 是唯一
人工审批源”的 M3 边界。除非上游提供服务端强制的只读 token/tool allowlist，或者
另有经过审计的只读代理，否则该 MCP 保持未安装、未配置。不能靠提示词要求模型
“只读”。

## 提供的工具

| 工具 | 说明 |
|---|---|
| `qd_fleet_status` | 每 job 最后状态 + run 计数 + 投影积压 |
| `qd_runs` | 最近 runs（可按 job 过滤） |
| `qd_run_events` | 单 run 完整事件链（started/finished/acks） |
| `qd_projection_backlog` | 未投影事件数、最老时间戳、按 job 分布 |
| `qd_artifacts` | artifact lineage（可按 run 过滤） |
| `qd_artifact_verify` | 对一个 registration 重新计算 CAS hash |
| `qd_watchdog` | overdue / never-run / unsupported（fail-closed）裁决 |
| `qd_project_now` | 立即排空投影（at-least-once + reconciliation） |
| `qd_workflows` | 列出本地 `0600` 白名单中的可启动 workflow id |
| `qd_workflow_start` | 按固定 id 异步启动；不接受 command/path/env/额外参数 |
| `qd_workflow_status` | 按 ledger 折叠 requested/dispatched/running/terminal 状态 |

验证：`npx @modelcontextprotocol/inspector ~/.local/bin/qd mcp` 应列出全部 11 个工具。
2026-07-13 的 AionUi 内置 Check MCP Availability 和随后一次独立 stdio 握手均列出
原 8 个只读/投影工具；安装包含 ADR-0004 的 wheel 后必须重新检查 11 工具并执行一次
真实 Manual Task，才能关闭一键启动验收。
