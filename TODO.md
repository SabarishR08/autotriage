# autotriage â€” daily improvement backlog
# Agent picks the first unchecked item each time this repo is scheduled.
# IMPORTANT: reference actual filenames so the context gatherer picks up the right files.

- [x] Add docstring to the main triage entry-point function explaining its input/output contract
- [x] Add a __version__ = "0.1.0" constant to the package __init__.py
- [x] Add type hints to any function missing them in app/api/logs.py
- [ ] Add type hints to any function missing them in app/services/triage_service.py
- [ ] Add a module-level docstring to app/api/logs.py explaining its purpose
- [ ] Add a module-level docstring to app/services/triage_service.py explaining its purpose
- [ ] Add input validation in app/api/logs.py to reject empty payloads with HTTP 422
- [ ] Add a top-level try/except in app/main.py that logs unhandled exceptions and exits 1
- [ ] Replace bare print() calls with logging.getLogger(__name__) in app/services/triage_service.py
- [ ] Replace bare print() calls with logging.getLogger(__name__) in app/api/logs.py
- [ ] Add a CONTRIBUTING.md with setup steps: clone, create venv, pip install -r requirements.txt
- [ ] Add a .editorconfig file enforcing 4-space indent, UTF-8, and trailing newline
- [ ] Add a .gitattributes file to normalise line endings (text=auto eol=lf)
- [ ] Add a constants.py module in app/core/ with project-wide string literals
- [ ] Add __all__ exports to app/services/__init__.py
- [ ] Add __all__ exports to app/api/__init__.py
- [ ] Add a simple healthcheck endpoint to app/api/health.py returning version from app/__init__.py
- [ ] Extract magic numbers and hardcoded timeouts into named constants in app/core/config.py
- [ ] Add a requirements-dev.txt with pytest and ruff as dev dependencies
- [ ] Add response time tracking to app/api/logs.py: log elapsed ms for each request
- [ ] Add a truncate_log(text, max_chars=4000) utility to app/services/triage_service.py
- [ ] Add a deduplicate_errors() utility to app/services/triage_service.py
- [ ] Add a stack_trace_hash() function in app/services/triage_service.py using hashlib
- [ ] Add a rate_limit_aware_call() wrapper in app/services/llm_provider.py that sleeps on 429
- [ ] Add a simple retry helper (max 3 attempts, exponential backoff) in app/services/llm_provider.py
- [ ] Normalise exception messages to sentence case in app/api/logs.py
- [ ] Replace any bare except: with except Exception as e: in app/services/triage_service.py
- [ ] Add a confidence_score float field (0.0-1.0) to the triage result in app/models/schemas.py
- [ ] Add an error_code field to the triage result schema in app/models/schemas.py
- [ ] Add a pydantic model for the triage result in app/models/schemas.py replacing plain dict returns
