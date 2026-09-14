# C3 · worker — Celery. This image carries FFmpeg and the agents' dependencies; the API image carries neither.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir -p /data/artifacts && chown app /data/artifacts

COPY constraints.txt ./
COPY contracts/ contracts/
COPY db/ db/
COPY adapters/ adapters/
COPY exporters/ exporters/
COPY worker/ worker/
COPY agents/ agents/
COPY scripts/worker-entrypoint.sh /usr/local/bin/worker-entrypoint

# ---- development: editable installs; new agent folders are installed on start
FROM base AS dev
RUN pip install -c constraints.txt watchfiles && pip install -c constraints.txt --config-settings editable_mode=compat \
      -e ./contracts -e ./db -e "./adapters[all]" -e ./exporters -e ./worker \
      $(for a in agents/*/; do printf -- '-e ./%s ' "${a%/}"; done)
RUN chown -R app /usr/local/lib/python3.11/site-packages
USER app
ENTRYPOINT ["worker-entrypoint"]
CMD ["watchfiles", "--filter", "python", "celery -A worker.celery_app worker --loglevel=INFO --concurrency=2", "/app/worker/src", "/app/agents", "/app/adapters/src", "/app/exporters/src", "/app/contracts/src"]

# ---- production
FROM base AS prod
RUN pip install -c constraints.txt ./contracts ./db "./adapters[all]" ./exporters ./worker \
      $(for a in agents/*/; do printf -- './%s ' "${a%/}"; done)
USER app
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
