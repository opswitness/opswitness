# AionUi 作为 Quarterdeck 控制台

界面策略（研究结论）：**不自研前端**。三层现成界面：

1. **Paperclip Web UI**（http://127.0.0.1:3100）— 舰队 issue（`[qd] <job>`）、run 评论、
   审批队列、成本看板，投影后自动出现，零配置。
2. **AionUi 对话式控制台** — 挂两个 MCP server，自然语言查舰队、批审批：
   - Paperclip 官方 MCP（35 个任务工具）
   - Quarterdeck MCP（本文件，补官方没有的：外部舰队 ledger / watchdog / 投影控制）
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
的 env/SQLite。若只需读工具，`qd_project_now` 不应由模型调用。

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
| `qd_project_now` | 立即排空投影（唯一写操作，at-least-once） |

验证：`npx @modelcontextprotocol/inspector ~/.local/bin/qd mcp` 应列出全部 8 个工具。
