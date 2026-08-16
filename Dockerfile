# ── Stage 1: build deps ─────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install only production dependencies into an isolated prefix
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements/base.txt


# ── Stage 2: production image ────────────────────────────────────────────────
FROM python:3.11-slim AS production

# Non-root user — never run app containers as root
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy only the installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source (no .env, no *.db, no tests — see .dockerignore)
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Own the workdir as the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Docker-level liveness check — uses the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8000/health', timeout=8); \
         sys.exit(0 if r.status == 200 else 1)"

# Single worker by default; scale via WEB_CONCURRENCY env var (Render sets it automatically)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
