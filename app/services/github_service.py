"""
GitHub integration.

AutoTriage is agentless: it never installs anything in the target repo. It
only needs read access (to pull source files referenced in a stack trace)
and, optionally, write access to open a pull request with the generated fix.
"""

import re

from app.core.config import get_settings


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

    def extract_file_paths(self, stack_trace: str) -> list[str]:
        """Best-effort extraction of source file paths referenced in a trace."""
        pattern = r"([\w./-]+\.(?:py|js|ts|java|go|rb))"
        matches = re.findall(pattern, stack_trace)
        # de-dupe while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered

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

    def open_pull_request(
        self,
        title: str,
        body: str,
        branch_name: str,
        base_branch: str = "main",
        patch_diff: str | None = None,
    ) -> str:
        """
        Open a PR with the given title/body. Applying `patch_diff` to a new
        branch is implementation-specific to the target repo's structure;
        this method creates the branch and PR shell so the diff can be
        committed by whichever step follows (manual review, CI job, etc.).
        """
        if not self.is_configured:
            raise GitHubServiceError("GitHub is not configured (missing token/repo).")

        base_ref = self._repo.get_git_ref(f"heads/{base_branch}")
        self._repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_ref.object.sha)

        pr = self._repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=base_branch,
        )
        return pr.html_url
