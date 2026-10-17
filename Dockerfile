FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM python:3.11-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN useradd --create-home appuser \
    && mkdir -p /app/data/db /app/data/chroma /app/data/index_manifests \
    && chown -R appuser:appuser /app
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser data/knowledge/ ./data/knowledge/
COPY --chown=appuser:appuser data/scenarios/ ./data/scenarios/
COPY --chown=appuser:appuser scripts/seed_demo_users.py scripts/check_copilot_index.py scripts/init_database.py ./scripts/

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=5)" || exit 1
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
