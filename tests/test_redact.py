from quarterdeck.redact import redact_argv, redact_text

SK = "sk-" + "a1B2" * 8  # 32 chars after prefix


def test_flag_with_equals_masked():
    out = redact_argv([f"--api-key={SK}", "run"])
    assert out[0] == "--api-key=«redacted»" and out[1] == "run"


def test_flag_with_separate_value_masked():
    out = redact_argv(["--token", "hunter2-short", "positional"])
    assert out == ["--token", "«redacted»", "positional"]


def test_provider_shaped_secret_in_positional_masked():
    out = redact_argv(["deploy", SK])
    assert out == ["deploy", "«redacted»"]


def test_paths_and_urls_survive():
    long_path = "/Users/someone/trade/quarterdeck/src/quarterdeck/wrap/runner_module_file.py"
    url = "https://api.example.com/v1/companies/abc/issues?limit=50&status=open"
    assert redact_text(long_path) == long_path
    assert redact_text(url) == url


def test_long_opaque_string_masked():
    blob = "A" * 48
    assert redact_text(f"key {blob} end") == "key «redacted» end"
