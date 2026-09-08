"""Django settings for the Reconciliation Workbench foundation."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_nonnegative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be a nonnegative integer") from error
    if value < 0:
        raise ImproperlyConfigured(f"{name} must be a nonnegative integer")
    return value


ENVIRONMENT = os.getenv("DJANGO_ENV", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"
DEBUG = env_bool("DJANGO_DEBUG", default=not IS_PRODUCTION)

_secret_key = os.getenv("DJANGO_SECRET_KEY")
_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS")
_trusted_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS")
_database_url = os.getenv("DATABASE_URL")

if IS_PRODUCTION:
    missing = [
        name
        for name, value in (
            ("DJANGO_SECRET_KEY", _secret_key),
            ("DJANGO_ALLOWED_HOSTS", _allowed_hosts),
            ("DJANGO_CSRF_TRUSTED_ORIGINS", _trusted_origins),
            ("DATABASE_URL", _database_url),
        )
        if not value
    ]
    if missing:
        raise ImproperlyConfigured(
            "Production configuration is missing: " + ", ".join(missing)
        )

SECRET_KEY = _secret_key or "unsafe-development-key"
ALLOWED_HOSTS = env_csv(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
)
CSRF_TRUSTED_ORIGINS = env_csv("DJANGO_CSRF_TRUSTED_ORIGINS", "")

if IS_PRODUCTION:
    insecure = []
    if DEBUG:
        insecure.append("DJANGO_DEBUG must be false")
    if len(SECRET_KEY) < 32:
        insecure.append("DJANGO_SECRET_KEY must contain at least 32 characters")
    if "*" in ALLOWED_HOSTS:
        insecure.append("DJANGO_ALLOWED_HOSTS must not contain a wildcard")
    if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
        insecure.append("DJANGO_CSRF_TRUSTED_ORIGINS must use HTTPS")
    if insecure:
        raise ImproperlyConfigured("; ".join(insecure))

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "workspaces",
    "books",
    "sources",
    "ingestion",
    "resolutions",
    "reconciliation",
    "cases",
    "jobs",
    "foundation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "observability.middleware.CorrelationLoggingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "workspaces.middleware.WorkspaceMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

def database_configuration() -> dict[str, object]:
    if not _database_url:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "reconciliation"),
            "USER": os.getenv("DB_USER", "reconciliation"),
            "PASSWORD": os.getenv("DB_PASSWORD", "reconciliation-local-only"),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "55432"),
            "CONN_MAX_AGE": 0,
        }

    parsed = urlparse(_database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL URL")
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ImproperlyConfigured("DATABASE_URL must include a database name")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(database_name),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60 if IS_PRODUCTION else 0,
    }


DATABASES = {"default": database_configuration()}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_HSTS_SECONDS = 31_536_000 if IS_PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = IS_PRODUCTION

WORKSPACE_RETAINED_BYTES_LIMIT = env_nonnegative_int(
    "WORKSPACE_RETAINED_BYTES_LIMIT", 250 * 1024 * 1024
)
WORKSPACE_BOOK_LIMIT = env_nonnegative_int("WORKSPACE_BOOK_LIMIT", 10)
WORKSPACE_ACTIVE_JOB_LIMIT = env_nonnegative_int("WORKSPACE_ACTIVE_JOB_LIMIT", 10)

INGESTION_PRIVATE_ROOT = Path(
    os.getenv("INGESTION_PRIVATE_ROOT", BASE_DIR / ".private-artifacts")
).resolve()
INGESTION_STORAGE_BACKEND = os.getenv("INGESTION_STORAGE_BACKEND", "local")
INGESTION_S3_BUCKET = os.getenv("INGESTION_S3_BUCKET", "")
INGESTION_S3_REGION = os.getenv("INGESTION_S3_REGION") or None
INGESTION_S3_ENDPOINT_URL = os.getenv("INGESTION_S3_ENDPOINT_URL") or None
INGESTION_S3_CACHE_ROOT = Path(
    os.getenv("INGESTION_S3_CACHE_ROOT", BASE_DIR / ".private-artifacts-cache")
).resolve()
INGESTION_MAX_BYTES = env_nonnegative_int(
    "INGESTION_MAX_BYTES", 25 * 1024 * 1024
)
INGESTION_MAX_ROWS = env_nonnegative_int("INGESTION_MAX_ROWS", 10_000)
INGESTION_MAX_COLUMNS = env_nonnegative_int("INGESTION_MAX_COLUMNS", 100)
INGESTION_MAX_FIELD_CHARACTERS = env_nonnegative_int(
    "INGESTION_MAX_FIELD_CHARACTERS", 4_096
)

JOBS_RUN_MAX_ATTEMPTS = env_nonnegative_int("JOBS_RUN_MAX_ATTEMPTS", 3)
JOBS_RUN_LEASE_SECONDS = env_nonnegative_int("JOBS_RUN_LEASE_SECONDS", 60)
JOBS_RUN_BACKOFF_SECONDS = env_nonnegative_int("JOBS_RUN_BACKOFF_SECONDS", 5)
JOBS_IMPORT_MAX_ATTEMPTS = env_nonnegative_int("JOBS_IMPORT_MAX_ATTEMPTS", 3)
JOBS_IMPORT_LEASE_SECONDS = env_nonnegative_int("JOBS_IMPORT_LEASE_SECONDS", 60)
JOBS_IMPORT_BACKOFF_SECONDS = env_nonnegative_int("JOBS_IMPORT_BACKOFF_SECONDS", 5)
JOBS_CLEANUP_MAX_ATTEMPTS = env_nonnegative_int("JOBS_CLEANUP_MAX_ATTEMPTS", 3)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "privacy_safe_json": {
            "()": "observability.logging.PrivacySafeJsonFormatter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "privacy_safe_json",
        }
    },
    "loggers": {
        "reconciliation.requests": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        }
    },
}
