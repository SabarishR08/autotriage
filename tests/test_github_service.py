from app.services.github_service import (
    GitHubService,
    _apply_hunks,
    _split_diff_by_file,
)


# ------------------------------------------------------------------
# Traceback parsing — Python
# ------------------------------------------------------------------

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
    trace = (
        'File "app/foo.py", line 1, in bar\n'
        'File "app/foo.py", line 2, in baz\n'
        'File "app/bar.py", line 3, in qux\n'
    )
    paths = service.extract_file_paths(trace)
    assert paths == ["app/foo.py", "app/bar.py"]


# ------------------------------------------------------------------
# Traceback parsing — Node.js
# ------------------------------------------------------------------

def test_extract_file_paths_node_at_format():
    service = GitHubService(token=None, repo=None)
    trace = (
        "Error: Cannot read properties of undefined\n"
        "    at createOrder (src/services/orders.js:42:10)\n"
        "    at processOrder (src/controllers/checkout.ts:18:5)\n"
        "    at Layer.handle (node_modules/express/lib/router/layer.js:95:5)\n"
    )
    paths = service.extract_file_paths(trace)
    assert "src/services/orders.js" in paths
    assert "src/controllers/checkout.ts" in paths
    # node_modules should still be included (caller can filter)
    assert len(paths) == 3


def test_extract_file_paths_node_no_function_name():
    service = GitHubService(token=None, repo=None)
    trace = "    at src/utils/math.js:10:5\n"
    paths = service.extract_file_paths(trace)
    assert "src/utils/math.js" in paths


# ------------------------------------------------------------------
# Traceback parsing — Java
# ------------------------------------------------------------------

def test_extract_file_paths_java():
    service = GitHubService(token=None, repo=None)
    trace = (
        "java.lang.NullPointerException\n"
        "\tat com.example.service.OrderService.createOrder(OrderService.java:42)\n"
        "\tat com.example.controller.CheckoutController.checkout(CheckoutController.java:18)\n"
    )
    paths = service.extract_file_paths(trace)
    assert any("OrderService.java" in p for p in paths)
    assert any("CheckoutController.java" in p for p in paths)


# ------------------------------------------------------------------
# Unconfigured GitHub
# ------------------------------------------------------------------

def test_fetch_source_context_without_config():
    service = GitHubService(token="", repo="")
    assert service.is_configured is False
    result = service.fetch_source_context(["app/foo.py"])
    assert "not configured" in result.lower() or "no source context" in result.lower()


# ------------------------------------------------------------------
# Diff parsing helpers
# ------------------------------------------------------------------

def test_split_diff_by_file_single_file():
    diff = (
        "--- a/app/utils/math.py\n"
        "+++ b/app/utils/math.py\n"
        "@@ -1,3 +1,5 @@\n"
        " # math.py\n"
        " def calculate_total(items):\n"
        "+    if not items:\n"
        "+        raise ValueError('empty')\n"
        "     return sum(item['price'] for item in items) / len(items)\n"
    )
    result = _split_diff_by_file(diff)
    assert "app/utils/math.py" in result
    assert len(result) == 1


def test_split_diff_by_file_multiple_files():
    diff = (
        "--- a/app/a.py\n+++ b/app/a.py\n@@ -1 +1 @@\n-old\n+new\n"
        "--- a/app/b.py\n+++ b/app/b.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    result = _split_diff_by_file(diff)
    assert set(result.keys()) == {"app/a.py", "app/b.py"}


def test_split_diff_strips_b_prefix():
    diff = "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-x\n+y\n"
    result = _split_diff_by_file(diff)
    assert "src/foo.py" in result
    assert "b/src/foo.py" not in result


def test_apply_hunks_add_lines():
    original = "line1\nline2\nline3\n"
    hunks = [
        "@@ -2,1 +2,2 @@\n",
        " line2\n",
        "+inserted\n",
    ]
    result = _apply_hunks(original, hunks)
    assert "inserted" in result
    assert "line1" in result
    assert "line3" in result


def test_apply_hunks_remove_lines():
    original = "line1\nbad_line\nline3\n"
    hunks = [
        "@@ -1,3 +1,2 @@\n",
        " line1\n",
        "-bad_line\n",
        " line3\n",
    ]
    result = _apply_hunks(original, hunks)
    assert "bad_line" not in result
    assert "line1" in result
    assert "line3" in result


def test_apply_hunks_empty_original_new_file():
    """Applying a diff to an empty original creates a new file."""
    original = ""
    hunks = [
        "@@ -0,0 +1,2 @@\n",
        "+line1\n",
        "+line2\n",
    ]
    result = _apply_hunks(original, hunks)
    assert result == "line1\nline2\n"
