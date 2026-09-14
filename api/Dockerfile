# C2 · api — FastAPI. No FFmpeg, no agents, no adapters: if you ever add them here, a boundary has been crossed.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir -p /data/artifacts && chown app /data/artifacts

COPY constraints.txt ./
COPY contracts/ contracts/
COPY db/ db/
COPY api/ api/

# ---- development: editable installs so the mounted source hot-reloads
FROM base AS dev
RUN pip install -c constraints.txt --config-settings editable_mode=compat -e ./contracts -e ./db -e "./api[test]"
USER app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/api/src", "--reload-dir", "/app/contracts/src", "--reload-dir", "/app/db/src"]

# ---- production
FROM base AS prod
RUN pip install -c constraints.txt ./contracts ./db ./api && rm -rf contracts/src db/src api/src
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
