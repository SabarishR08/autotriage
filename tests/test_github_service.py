from app.services.github_service import GitHubService


def test_extract_file_paths_from_python_traceback():
    service = GitHubService(token=None, repo=None)  # unconfigured, extraction still works
    trace = (
        "Traceback (most recent call last):\n"
        '  File "app/services/orders.py", line 42, in create_order\n'
        "    total = calculate_total(items)\n"
        '  File "app/utils/math.py", line 10, in calculate_total\n'
        "ZeroDivisionError: division by zero"
    )
    paths = service.extract_file_paths(trace)
    assert "app/services/orders.py" in paths
    assert "app/utils/math.py" in paths
    assert len(paths) == 2


def test_extract_file_paths_dedupes():
    service = GitHubService(token=None, repo=None)
    trace = 'app/foo.py\napp/foo.py\napp/bar.py'
    paths = service.extract_file_paths(trace)
    assert paths == ["app/foo.py", "app/bar.py"]


def test_fetch_source_context_without_config():
    service = GitHubService(token=None, repo=None)
    assert service.is_configured is False
    result = service.fetch_source_context(["app/foo.py"])
    assert "not configured" in result.lower() or "no source context" in result.lower()
