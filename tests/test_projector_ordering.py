import respx
from httpx import Response

from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipClient
from quarterdeck.projector import Projector

BASE = "http://pp.test"


def _seed(led: Ledger, job: str) -> None:
    assert led.append("run_started", f"R-{job}", {"job": job, "argv": ["true"]})
    assert led.append(
        "run_finished",
        f"R-{job}",
        {"job": job, "exit_code": 0, "status": "succeeded", "duration_s": 0.1},
    )


@respx.mock
def test_failed_event_blocks_later_events_of_same_job(tmp_path):
    led = Ledger(tmp_path / "ledger")
    _seed(led, "demo")
    respx.get(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(200, json={"issues": [{"id": "iss-1", "title": "[qd] demo"}]})
    )
    respx.get(f"{BASE}/api/issues/iss-1/comments").mock(
        return_value=Response(200, json={"comments": []})
    )
    posted = respx.post(f"{BASE}/api/issues/iss-1/comments").mock(
        side_effect=[Response(500, text="boom"), Response(200, json={"id": "c-2"})]
    )

    stats = Projector(led, PaperclipClient(BASE, "k", "c1"), tmp_path / "lease").drain()
    # run_started failed -> run_finished must NOT be attempted this drain,
    # otherwise the remote issue would show finished before started.
    assert posted.call_count == 1
    assert stats["skipped_errors"] == 1 and stats["blocked"] == 1
    assert stats["projected"] == 0 and stats["pending_after"] == 2


@respx.mock
def test_one_failing_job_does_not_starve_others(tmp_path):
    led = Ledger(tmp_path / "ledger")
    _seed(led, "bad")
    _seed(led, "good")
    respx.get(f"{BASE}/api/companies/c1/issues").mock(
        return_value=Response(
            200,
            json={
                "issues": [
                    {"id": "iss-bad", "title": "[qd] bad"},
                    {"id": "iss-good", "title": "[qd] good"},
                ]
            },
        )
    )
    respx.get(f"{BASE}/api/issues/iss-bad/comments").mock(
        return_value=Response(200, json={"comments": []})
    )
    respx.get(f"{BASE}/api/issues/iss-good/comments").mock(
        return_value=Response(200, json={"comments": []})
    )
    bad_post = respx.post(f"{BASE}/api/issues/iss-bad/comments").mock(
        return_value=Response(500, text="boom")
    )
    good_post = respx.post(f"{BASE}/api/issues/iss-good/comments").mock(
        return_value=Response(200, json={"id": "c"})
    )

    stats = Projector(led, PaperclipClient(BASE, "k", "c1"), tmp_path / "lease").drain()
    assert bad_post.call_count == 1  # fail-stop after first failure for 'bad'
    assert good_post.call_count == 2  # 'good' fully projected
    assert stats["projected"] == 2 and stats["skipped_errors"] == 1 and stats["blocked"] == 1
