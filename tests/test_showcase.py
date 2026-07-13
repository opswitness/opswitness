import json
import subprocess
import sys
from pathlib import Path


def test_synthetic_showcase_is_secret_free_and_end_to_end(tmp_path):
    script = Path(__file__).parents[1] / "examples" / "showcase" / "run.py"
    output = tmp_path / "showcase"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["gate"] == {"first": "defer", "second": "allow"}
    assert summary["outage_pending"] > 0
    assert summary["replay_projected"] > 0
    assert summary["no_repost_projected"] == 0
    assert summary["final_pending"] == 0
    assert summary["digest_healthy"] is True
    assert "outcome evidence" in (output / "digest.md").read_text()
