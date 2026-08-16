"""
GitHub integration.

AutoTriage is agentless: it never installs anything in the target repo. It
only needs read access (to pull source files referenced in a stack trace)
and, optionally, write access to open a pull request with the generated fix.
"""

import base64
import logging
import re

from app.core.config import get_settings

logger = logging.getLogger("autotriage.github")


class GitHubServiceError(RuntimeError):
    pass


class GitHubService:
    def __init__(self, token: str | None = None, repo: str | None = None):
        settings = get_settings()
        # Fall back to settings only when the caller passes None explicitly.
        # An empty string means "force unconfigured" (used in tests and health checks).
        self._token = settings.GITHUB_TOKEN if token is None else token
        self._repo_name = settings.GITHUB_REPO if repo is None else repo

        if not self._token or not self._repo_name:
            self._client = None
            self._repo = None
            return

        try:
            from github import Github
        except ImportError as exc:  # pragma: no cover
            raise GitHubServiceError(
                "PyGithub not installed. Run: pip install PyGithub"
            ) from exc

        self._client = Github(self._token)
        self._repo = self._client.get_repo(self._repo_name)

    @property
    def is_configured(self) -> bool:
        return self._repo is not None

    # ------------------------------------------------------------------
    # Traceback parsing — structured multi-language parsers
    # ------------------------------------------------------------------

    def extract_file_paths(self, stack_trace: str) -> list[str]:
        """
        Extract source file paths from a stack trace.

        Tries language-specific parsers in order (Python → Node/JS → Java),
        then falls back to a general regex if none match. Returns a
        deduplicated, order-preserving list of relative file paths.
        """
        paths = (
            self._parse_python(stack_trace)
            or self._parse_node(stack_trace)
            or self._parse_java(stack_trace)
            or self._parse_generic(stack_trace)
        )
        return paths

    def _parse_python(self, trace: str) -> list[str]:
        """
        Python traceback format:
          File "path/to/file.py", line N, in function_name
        """
        matches = re.findall(r'File "([^"]+\.py)", line \d+', trace)
        return _dedup(matches)

    def _parse_node(self, trace: str) -> list[str]:
        """
        Node.js / V8 format:
          at FunctionName (path/to/file.js:line:col)
          at path/to/file.js:line:col
        Also handles TypeScript (.ts) and compiled maps (.mjs).
        """
        # Both "at X (file:line:col)" and "at file:line:col"
        matches = re.findall(
            r"at (?:[^\s(]+\s+\()?([^\s()\n]+\.(?:js|ts|mjs|cjs)):\d+:\d+\)?",
            trace,
        )
        return _dedup(matches)

    def _parse_java(self, trace: str) -> list[str]:
        """
        Java format:
          at com.example.ClassName.method(FileName.java:line)
        Converts package+classname to a probable path.
        """
        raw = re.findall(
            r"at ((?:[a-zA-Z_$][a-zA-Z0-9_$]*\.)+[a-zA-Z_$][a-zA-Z0-9_$]*)\."
            r"[a-zA-Z_$<][a-zA-Z0-9_$>]*\([A-Za-z0-9_$]+\.java:\d+\)",
            trace,
        )
        paths: list[str] = []
        for fqcn in raw:
            parts = fqcn.split(".")
            # heuristic: last two segments are OuterClass[.InnerClass]
            pkg_path = "/".join(parts[:-1])
            class_file = parts[-1] + ".java"
            paths.append(f"{pkg_path}/{class_file}")
        return _dedup(paths)

    def _parse_generic(self, trace: str) -> list[str]:
        """Fallback: any token that looks like a relative file path."""
        matches = re.findall(r"([\w./-]+\.(?:py|js|ts|java|go|rb|mjs|cjs))", trace)
        return _dedup(matches)

    # ------------------------------------------------------------------
    # Source fetching
    # ------------------------------------------------------------------

    def fetch_source_context(self, file_paths: list[str], max_files: int = 5) -> str:
        """Fetch the content of the given files from the configured repo."""
        if not self.is_configured:
            return "(GitHub not configured — no source context available.)"

        chunks: list[str] = []
        for path in file_paths[:max_files]:
            try:
                content_file = self._repo.get_contents(path)
                content = content_file.decoded_content.decode("utf-8", errors="replace")
                chunks.append(f"--- {path} ---\n{content}")
            except Exception as exc:  # noqa: BLE001
                chunks.append(f"--- {path} --- (could not fetch: {exc})")

        return "\n\n".join(chunks) if chunks else "(No matching files found in repo.)"

    # ------------------------------------------------------------------
    # Pull request creation with real patch commit
    # ------------------------------------------------------------------

    def open_pull_request(
        self,
        title: str,
        body: str,
        branch_name: str,
        base_branch: str = "main",
        patch_diff: str | None = None,
    ) -> str:
        """
        Create a branch, commit any patch changes, then open a PR.

        If `patch_diff` is a valid unified diff, each changed file is
        committed to the new branch via the GitHub Contents API before
        the PR is opened — so reviewers see a real file diff, not just
        a text block in the PR description.
        """
        if not self.is_configured:
            raise GitHubServiceError("GitHub is not configured (missing token/repo).")

        # Create the branch off base
        base_ref = self._repo.get_git_ref(f"heads/{base_branch}")
        self._repo.create_git_ref(
            ref=f"refs/heads/{branch_name}", sha=base_ref.object.sha
        )
        logger.info("Created branch %s from %s", branch_name, base_branch)

        # Apply the diff as real file commits on the new branch
        committed_files: list[str] = []
        if patch_diff:
            committed_files = self._apply_patch(branch_name, patch_diff)

        # Build PR body
        files_note = (
            f"\n\n**Files committed:** {', '.join(f'`{f}`' for f in committed_files)}"
            if committed_files
            else "\n\n_Patch diff is in the description above — no files were auto-committed (diff could not be parsed)._"
        )

        pr = self._repo.create_pull(
            title=title,
            body=body + files_note,
            head=branch_name,
            base=base_branch,
        )
        logger.info("Opened PR #%s: %s", pr.number, pr.html_url)
        return pr.html_url

    def _apply_patch(self, branch_name: str, patch_diff: str) -> list[str]:
        """
        Parse a unified diff and commit each changed file to `branch_name`.

        Supports the subset of unified diff that LLMs typically produce:
          --- a/path/to/file.py   (or  --- path/to/file.py)
          +++ b/path/to/file.py   (or  +++ path/to/file.py)
          @@ ... @@
          [context / +added / -removed lines]

        Returns a list of file paths that were successfully committed.
        """
        file_patches = _split_diff_by_file(patch_diff)
        committed: list[str] = []

        for file_path, hunks in file_patches.items():
            try:
                # Fetch current file content from the branch
                try:
                    content_obj = self._repo.get_contents(file_path, ref=branch_name)
                    original = content_obj.decoded_content.decode("utf-8", errors="replace")
                    sha = content_obj.sha
                except Exception:  # file doesn't exist yet — new file
                    original = ""
                    sha = None

                patched = _apply_hunks(original, hunks)

                encoded = base64.b64encode(patched.encode("utf-8")).decode("ascii")
                commit_msg = f"AutoTriage: apply patch to {file_path}"

                if sha:
                    self._repo.update_file(
                        path=file_path,
                        message=commit_msg,
                        content=encoded,
                        sha=sha,
                        branch=branch_name,
                    )
                else:
                    self._repo.create_file(
                        path=file_path,
                        message=commit_msg,
                        content=encoded,
                        branch=branch_name,
                    )

                committed.append(file_path)
                logger.info("Committed patch to %s on branch %s", file_path, branch_name)

            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not apply patch to %s: %s", file_path, exc)

        return committed


# ------------------------------------------------------------------
# Diff parsing helpers
# ------------------------------------------------------------------

def _dedup(items: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _split_diff_by_file(patch_diff: str) -> dict[str, list[str]]:
    """
    Split a unified diff string into a dict of {file_path: [hunk_strings]}.
    Handles both  --- a/path  and  --- path  prefixes.
    """
    file_patches: dict[str, list[str]] = {}
    current_file: str | None = None
    current_hunks: list[str] = []

    for line in patch_diff.splitlines(keepends=True):
        if line.startswith("+++ "):
            # Save previous file
            if current_file and current_hunks:
                file_patches[current_file] = current_hunks
            # Extract path — strip b/ prefix if present
            raw_path = line[4:].strip()
            if raw_path.startswith("b/"):
                raw_path = raw_path[2:]
            current_file = raw_path
            current_hunks = []
        elif line.startswith("--- "):
            continue  # skip the --- line, we key on +++
        elif current_file is not None:
            current_hunks.append(line)

    if current_file and current_hunks:
        file_patches[current_file] = current_hunks

    return file_patches


def _apply_hunks(original: str, hunk_lines: list[str]) -> str:
    """
    Apply a list of unified diff hunk lines to `original` text.
    Returns the patched file content.

    This is a straightforward line-by-line apply — sufficient for the
    well-structured diffs produced by LLMs on small files.
    """
    orig_lines = original.splitlines(keepends=True)
    result: list[str] = []
    orig_idx = 0  # 0-based index into orig_lines

    i = 0
    while i < len(hunk_lines):
        line = hunk_lines[i]

        if line.startswith("@@ "):
            # Parse hunk header: @@ -start,count +start,count @@
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                orig_start = int(m.group(1)) - 1  # convert to 0-based
                # Copy unchanged lines from original up to hunk start
                while orig_idx < orig_start:
                    if orig_idx < len(orig_lines):
                        result.append(orig_lines[orig_idx])
                    orig_idx += 1
            i += 1
            continue

        if line.startswith("-"):
            # Removed line — skip it in original
            orig_idx += 1
        elif line.startswith("+"):
            # Added line — include in result (strip the leading +)
            result.append(line[1:])
        elif line.startswith(" ") or line.startswith("\\ "):
            # Context line — include from original
            if orig_idx < len(orig_lines):
                result.append(orig_lines[orig_idx])
            orig_idx += 1
        i += 1

    # Append any remaining original lines after the last hunk
    while orig_idx < len(orig_lines):
        result.append(orig_lines[orig_idx])
        orig_idx += 1

    return "".join(result)
