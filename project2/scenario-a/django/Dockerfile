# =============================================================================
# Project 2 — Scenario A, phase 1B
# Django 6.0.8 + Gunicorn + SQLite.
#
# Build:  docker build -t telecom-lab-django:0.1 project2/scenario-a/django
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=telecom_lab.settings

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The named volume is empty on first use: Docker copies this directory into it,
# ownership included, so the non-root user keeps write access to SQLite.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data /app/staticfiles \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Docker must be able to tell whether the application is operational.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/app/entrypoint.sh"]
