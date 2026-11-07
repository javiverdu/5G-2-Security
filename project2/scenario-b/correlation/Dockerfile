# =============================================================================
# Project 2 — Scenario B, phase 2E
# Correlation job: reads the current run's evidence and emits
# security-event-correlation.json/.md. It never scans and never invents data.
# =============================================================================
FROM python:3.12-slim

WORKDIR /app
COPY correlate.py /app/correlate.py

ENTRYPOINT ["python3", "/app/correlate.py"]
