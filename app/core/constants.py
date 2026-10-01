"""Project-wide string constants."""

# Application metadata
APP_NAME = "AutoTriage"
APP_VERSION = "0.1.0"

# API
API_PREFIX = "/api"
API_V1_PREFIX = "/api/v1"

# Health check
HEALTH_CHECK_PATH = "/health"

# GitHub
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_WEBHOOK_SECRET_HEADER = "X-Hub-Signature-256"
GITHUB_EVENT_HEADER = "X-GitHub-Event"
GITHUB_DELIVERY_HEADER = "X-GitHub-Delivery"

# Issue/PR labels
LABEL_BUG = "bug"
LABEL_FEATURE = "feature"
LABEL_DOCUMENTATION = "documentation"
LABEL_GOOD_FIRST_ISSUE = "good first issue"
LABEL_HELP_WANTED = "help wanted"
LABEL_PRIORITY_HIGH = "priority: high"
LABEL_PRIORITY_MEDIUM = "priority: medium"
LABEL_PRIORITY_LOW = "priority: low"
LABEL_STATUS_TRIAGE = "status: triage"
LABEL_STATUS_IN_PROGRESS = "status: in progress"
LABEL_STATUS_DONE = "status: done"

# Issue states
ISSUE_STATE_OPEN = "open"
ISSUE_STATE_CLOSED = "closed"

# PR states
PR_STATE_OPEN = "open"
PR_STATE_CLOSED = "closed"
PR_STATE_MERGED = "merged"

# LLM
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_DEFAULT_MODEL = "gpt-4o-mini"
LLM_MAX_TOKENS = 4000
LLM_TEMPERATURE = 0.1

# Database
DB_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Cache
CACHE_TTL_SECONDS = 300

# Logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Environment variables
ENV_DATABASE_URL = "DATABASE_URL"
ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
ENV_GITHUB_WEBHOOK_SECRET = "GITHUB_WEBHOOK_SECRET"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_APP_ENV = "APP_ENV"

# App environments
ENV_DEVELOPMENT = "development"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"
ENV_TESTING = "testing"
