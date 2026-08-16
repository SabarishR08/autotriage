This repo already has a working v1 of **AutoTriage** — do NOT rebuild from scratch. Read the existing code and README/docs first, then extend it. Push all changes to the `main` branch of the connected remote (https://github.com/SabarishR08/autotriage), committing incrementally with meaningful messages.

## What already exists (working, tested)

- FastAPI backend with SQLite/SQLAlchemy persistence (`app/`)
- `POST /api/v1/logs` — structured error log ingestion, runs triage as a background task
- `GET /api/v1/logs/{id}`, `GET /api/v1/logs`, `POST /api/v1/logs/{id}/retriage`
- `GithubService` — extracts file paths from stack traces via regex, fetches source from a configured repo, can open a PR
- LLM provider abstraction (`app/services/llm_provider.py`) supporting OpenAI and Anthropic behind one interface, selected via `LLM_PROVIDER` env var — caller supplies their own key
- `triage_service.run_triage` — orchestrates extraction → GitHub fetch → LLM call → persistence → optional PR
- 12 passing tests (`tests/`) covering ingestion, GitHub extraction, and LLM response parsing
- Dockerfile + docker-compose, `.env.example`, README with Mermaid architecture + sequence diagrams, full API docs, and `docs/ARCHITECTURE.md`

Run `pytest tests/ -v` first to confirm the baseline still passes before making changes.

## What to build next

1. **Frontend dashboard** (React + Vite + Tailwind) — list ingested errors with status, drill into a single error to see root cause / suggested fix / patch diff / PR link, trigger retriage from the UI.
2. **Patch application** — currently `open_pull_request` creates a branch + PR shell with the diff described in the PR body, but doesn't commit the diff as a real file change. Extend `GitHubService` to actually apply the unified diff as a commit on the new branch before opening the PR.
3. **Structured multi-language traceback parsing** — replace/extend the current regex-based `extract_file_paths` with proper parsers for Python, Node/JS, and Java stack trace formats, since the current approach is intentionally simple (see `docs/ARCHITECTURE.md` → Known Constraints).
4. **Durable background processing** — swap `BackgroundTasks` for a real queue (e.g. Celery + Redis, or RQ) so triage survives a server restart, per the same "Known Constraints" section.
5. **Auth on the ingestion endpoint** — currently open; add an API-key header check so only authorized services can submit logs.
6. **Analytics endpoint** — aggregate recurring failure patterns across services (top root causes, most-frequently-affected files) for the "team-wide analytics" item in the README's Future Scope.

## Requirements while extending

- Keep the LLM provider and GitHub service abstractions intact — don't hardcode a single provider or break the swappable interface.
- Any new env vars go in `.env.example` with a comment, never committed with real values.
- Add tests for anything new; keep the existing 12 passing.
- Update `README.md` and `docs/ARCHITECTURE.md` to reflect new components — keep the Mermaid diagrams current (add new ones for new subsystems, e.g. a diagram for the queue-based background processing once added).
- Don't reference this being adapted from any other project or challenge — this is AutoTriage, a standalone project.

## Deliverable

Working code pushed to the remote, README/docs updated to match the current state of the system, all tests passing.
