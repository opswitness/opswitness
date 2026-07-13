import pytest

from quarterdeck.redact import redact_argv, redact_text

SK = "sk-" + "a1B2" * 8  # 32 chars after prefix
SHORT_SENTINEL = "short" + "-value"


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
    author_url = "https://example.test/books?author=alice&mode=open"
    assert redact_text(long_path) == long_path
    assert redact_text(url) == url
    assert redact_text(author_url) == author_url
    assert redact_argv(["--author", "alice"]) == ["--author", "alice"]


def test_long_opaque_string_masked():
    blob = "A" * 48
    assert redact_text(f"key {blob} end") == "key «redacted» end"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("API_KEY=hunter2 deploy", "API_KEY=«redacted» deploy"),
        ("export BOT_TOKEN='short secret'; run", "export BOT_TOKEN='«redacted»'; run"),
        (
            "curl --api-key tiny-value https://example.test",
            "curl --api-key «redacted» https://example.test",
        ),
        (
            f"curl -H 'Authorization: Bearer {SHORT_SENTINEL}' https://example.test",
            "curl -H 'Authorization: Bearer «redacted»' https://example.test",
        ),
        ('echo \'{"password":"tiny"}\'', 'echo \'{"password":"«redacted»"}\''),
        (
            "https://example.test/?token=short&mode=check",
            "https://example.test/?token=«redacted»&mode=check",
        ),
        (
            "curl -H 'X-Api-Key: tiny' https://example.test",
            "curl -H 'X-Api-Key: «redacted»' https://example.test",
        ),
    ],
)
def test_redact_text_masks_contextual_short_secrets(raw: str, expected: str):
    assert redact_text(raw) == expected
