"""Names shared by the API (producer) and the worker (consumer). Strings only — no Celery import."""

RUN_WORKFLOW_TASK = "gp.run_workflow"
"""Celery task name. The job payload is the run id and nothing else."""

CATALOG_REDIS_KEY = "gp:agents:catalog"
"""The worker writes the agent catalog (JSON list of AgentManifest) here on startup; the API reads it."""
