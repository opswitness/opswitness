import anyio
import pytest

from quarterdeck import mcp_server
from quarterdeck.ledger import Ledger


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_LEDGER_DIR", str(tmp_path / "ledger"))
    # Never let a unit test inherit the operator's real Paperclip credentials.
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "config"))
    led = Ledger((tmp_path / "ledger"))
    led.append("run_started", "01MCP", {"job": "feed-monitor", "argv": ["true"]})
    led.append(
        "run_finished",
        "01MCP",
        {"job": "feed-monitor", "exit_code": 0, "status": "succeeded", "duration_s": 1.0},
    )
    return tmp_path


def test_underlying_functions(seeded_env):
    status = mcp_server.fleet_status()
    assert status["runs"] == 1 and status["jobs"][0]["job"] == "feed-monitor"

    rs = mcp_server.runs()
    assert rs[0]["status"] == "succeeded"

    chain = mcp_server.run_events("01MCP")
    assert [e["kind"] for e in chain] == ["run_started", "run_finished"]

    backlog = mcp_server.projection_backlog()
    assert backlog["pending"] == 2 and backlog["by_job"] == {"feed-monitor": 2}


def test_project_now_refuses_without_config(seeded_env, monkeypatch):
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    out = mcp_server.project_now()
    assert "error" in out  # unconfigured must not silently no-op


def test_server_exposes_all_tools(seeded_env):
    server = mcp_server.build_server()
    tools = anyio.run(server.list_tools)
    names = {t.name for t in tools}
    assert names == {
        "qd_fleet_status",
        "qd_runs",
        "qd_run_events",
        "qd_projection_backlog",
        "qd_watchdog",
        "qd_project_now",
    }


def test_tool_call_roundtrip(seeded_env):
    server = mcp_server.build_server()
    result = anyio.run(server.call_tool, "qd_fleet_status", {})
    text = result[0][0].text if isinstance(result, tuple) else result[0].text
    assert "feed-monitor" in text
