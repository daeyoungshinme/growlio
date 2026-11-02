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


def test_namedtuple_value_does_not_raise():
    from collections import namedtuple

    Pair = namedtuple("Pair", "a b")
    out = _redact_processor(None, "info", {"event": "x", "pair": Pair("Authorization: Bearer abc123secret", 1)})

    assert "abc123secret" not in str(out["pair"])
    assert out["pair"][1] == 1


def test_traceback_passes_through_redaction_before_rendering():
    """plans/109 C3 — exc_info를 렌더러가 직접 출력하면 예외 메시지의 시크릿이 그대로 남는다."""
    from app.core.logging import _with_redaction

    processors = _with_redaction([lambda _l, _m, event: event])
    try:
        raise ValueError("password=hunter2")
    except ValueError as exc:
        event = {"event": "unhandled_exception", "exc_info": exc}
        for processor in processors[:-1]:
            event = processor(None, "error", event)

    assert "exc_info" not in event
    assert "hunter2" not in event["exception"]
    assert "ValueError" in event["exception"]
