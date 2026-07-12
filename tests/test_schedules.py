from quarterdeck.schedules import classify_schedule, schedules_by_state


def test_shared_schedule_classifier():
    assert classify_schedule({"job": "a", "expected_interval_seconds": 60}) == "active"
    assert (
        classify_schedule({"job": "b", "expected_interval_seconds": 60, "enabled": False})
        == "disabled"
    )
    assert classify_schedule({"job": "c", "calendar": {"Hour": 7}}) == "unsupported"
    assert schedules_by_state(
        [
            {"job": "a", "expected_interval_seconds": 60},
            {"job": "b", "expected_interval_seconds": 60, "enabled": False},
            {"job": "c"},
        ]
    ) == {"active": ["a"], "disabled": ["b"], "unsupported": ["c"]}
