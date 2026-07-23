import anyio
import pytest

from opswitness import mcp_server
from opswitness.ledger import Ledger


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSWITNESS_LEDGER_DIR", str(tmp_path / "ledger"))
    # Never let a unit test inherit the operator's real Paperclip credentials.
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "config"))
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

    package = mcp_server.python_package_status("pytest")
    assert package["installed"] is True
    assert package["version"]
    assert mcp_server.python_package_status("not a package")["error"] == (
        "invalid package name"
    )


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
        "qd_artifacts",
        "qd_artifact_verify",
        "qd_python_package_status",
        "qd_request_input",
        "qd_watchdog",
        "qd_project_now",
        "qd_workflows",
        "qd_workflow_start",
        "qd_workflow_status",
    }


def test_tool_call_roundtrip(seeded_env):
    server = mcp_server.build_server()
    result = anyio.run(server.call_tool, "qd_fleet_status", {})
    text = result[0][0].text if isinstance(result, tuple) else result[0].text
    assert "feed-monitor" in text


def test_mail_mcp_surface_has_no_runtime_query_and_marks_open_world(seeded_env):
    server = mcp_server.build_server("mail")
    tools = anyio.run(server.list_tools)
    check = next(tool for tool in tools if tool.name == "qd_mail_check")
    assert check.inputSchema.get("properties") == {}
    assert check.annotations.readOnlyHint is True
    assert check.annotations.destructiveHint is False
    assert check.annotations.openWorldHint is True
    assert "untrusted" in (check.description or "")


def test_mail_profile_structurally_excludes_every_non_mail_tool(seeded_env):
    server = mcp_server.build_server("mail")
    tools = anyio.run(server.list_tools)
    assert {tool.name for tool in tools} == {"qd_mail_status", "qd_mail_check"}
    with pytest.raises(ValueError, match="unknown MCP profile"):
        mcp_server.build_server("unsafe")
