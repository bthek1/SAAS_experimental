from .test import *

# Playwright integration suite (frontend/playwright.integration.config.ts).
# Its own SQLite file, deleted and re-migrated at the start of every run.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "e2e.sqlite3",
    }
}

# The e2e Vite server is a different origin from the API on :8015.
CORS_ALLOWED_ORIGINS = ["http://localhost:5184"]
