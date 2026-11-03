from app.services.triage_service import truncate_log


def test_truncate_log_short_text():
    text = "Short log message"
    assert truncate_log(text, max_chars=4000) == text


def test_truncate_log_exceeds_max_chars():
    text = "a" * 5000
    truncated = truncate_log(text, max_chars=4000)
    assert len(truncated) == 4000
    assert truncated == "a" * 4000


def test_truncate_log_empty_or_none():
    assert truncate_log("", 4000) == ""
    assert truncate_log(None, 4000) is None
