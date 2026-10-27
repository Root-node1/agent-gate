"""Settings shared by every environment."""

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "allauth.account",
    "allauth.headless",
    "apps.accounts",
    "apps.agents",
    "apps.policies",
    "apps.payees",
    "apps.spend",
    "apps.approvals",
    "apps.payments",
    "apps.audit",
    "gate",
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def postgres_config(url: str) -> dict:
    """Build a Django database config from a PostgreSQL connection URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ImproperlyConfigured(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    name = unquote(parsed.path.lstrip("/"))
    if not name:
        raise ImproperlyConfigured("DATABASE_URL must include a database name.")
    try:
        conn_max_age = int(os.environ.get("DB_CONN_MAX_AGE", "0"))
    except ValueError as exc:
        raise ImproperlyConfigured("DB_CONN_MAX_AGE must be an integer.") from exc
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": conn_max_age,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": dict(parse_qsl(parsed.query)),
    }


def env_int(name: str, default: int) -> int:
    """Read a non-negative integer setting and fail clearly when it is malformed."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc
    if value < 0:
        raise ImproperlyConfigured(f"{name} must be zero or greater.")
    return value


TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 0)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {"default": postgres_config(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "agentgate",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.agents.authentication.AgentKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
    "DEFAULT_THROTTLE_RATES": {
        "agent": os.environ.get("THROTTLE_AGENT", "60/min"),
        "anon": os.environ.get("THROTTLE_ANON", "20/min"),
    },
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

ADMIN_PATH = os.environ.get("DJANGO_ADMIN_PATH", "admin").strip("/")
if not ADMIN_PATH:
    ADMIN_PATH = "admin"
ADMIN_PATH = f"{ADMIN_PATH}/"

DEMO_ORG_NAME = os.environ.get("DEMO_ORG_NAME", "demo")

SPECTACULAR_SETTINGS = {
    "TITLE": "AgentGate API",
    "DESCRIPTION": "Spending firewall between AI agents and PayPal.",
    "VERSION": "0.1.0",
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# The SPA reads the csrftoken cookie to send the X-CSRFToken header back.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

ACCOUNT_ALLOWED_SIGNUP_DOMAINS = [
    domain.strip().lower()
    for domain in os.environ.get("ACCOUNT_ALLOWED_SIGNUP_DOMAINS", "").split(",")
    if domain.strip()
]
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_LOGIN_METHODS = ["email"]
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_ADAPTER = "apps.accounts.adapters.CustomAccountAdapter"
LOGIN_REDIRECT_URL = os.environ.get("LOGIN_REDIRECT_URL", "/app/")
LOGOUT_REDIRECT_URL = os.environ.get("LOGOUT_REDIRECT_URL", "/login/")
