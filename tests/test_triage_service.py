from app.services.triage_service import truncate_log


def test_truncate_log_short():
    text = "Short error log"
    assert truncate_log(text, max_chars=100) == text


def test_truncate_log_exceeds():
    text = "a" * 5000
    truncated = truncate_log(text, max_chars=4000)
    assert len(truncated) == 4000
    assert truncated == "a" * 4000


def test_truncate_log_empty_or_none():
    assert truncate_log("") == ""
    assert truncate_log(None) is None
