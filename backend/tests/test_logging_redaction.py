"""app/core/logging.py redact 프로세서 — 구조화된 값(dict/list) 안의 비밀정보도 가린다."""

from __future__ import annotations

from app.core.logging import _redact_processor
from app.utils.masking import mask_account_no, mask_email


def test_redacts_sensitive_keys_inside_nested_dict():
    event = {
        "event": "kis_token_issue_failed",
        "response": {"access_token": "eyJabc.def.ghi", "detail": {"appsecret": "s3cr3tvalue"}, "msg1": "ok"},
    }

    out = _redact_processor(None, "error", event)

    assert out["response"]["access_token"] == "[REDACTED]"
    assert out["response"]["detail"]["appsecret"] == "[REDACTED]"
    assert out["response"]["msg1"] == "ok"


def test_redacts_secret_patterns_in_list_strings():
    out = _redact_processor(None, "error", {"event": "x", "body": ["Authorization: Bearer abcdef123456"]})

    assert "abcdef123456" not in out["body"][0]


def test_top_level_strings_still_redacted():
    out = _redact_processor(None, "error", {"event": "x", "error": "appkey=ABCDEFGH1234"})

    assert "ABCDEFGH1234" not in out["error"]


def test_mask_account_no_keeps_last_four():
    assert mask_account_no("5012345601") == "******5601"
    assert mask_account_no("123") == "***"
    assert mask_account_no(None) == ""


def test_mask_email():
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("not-an-email") == "***"
