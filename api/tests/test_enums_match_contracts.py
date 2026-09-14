"""`db` duplicates enum values so it can depend on nothing. This test catches drift."""

from contracts.run import MAX_RETRIES, ApprovalDecision, NodeStatus, OutputType, RunStatus
from db import models


def test_node_statuses_match():
    assert set(models.NODE_STATUSES) == {s.value for s in NodeStatus}


def test_run_statuses_match():
    assert set(models.RUN_STATUSES) == {s.value for s in RunStatus}


def test_output_types_and_decisions_match():
    assert set(models.OUTPUT_TYPES) == {s.value for s in OutputType}
    assert set(models.APPROVAL_DECISIONS) == {s.value for s in ApprovalDecision}


def test_retry_limit_matches():
    assert models.MAX_RETRIES == MAX_RETRIES
