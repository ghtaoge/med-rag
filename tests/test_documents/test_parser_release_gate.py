from types import SimpleNamespace

import pytest

from app.documents.jobs import ParseJobStatus, is_releaseable


@pytest.mark.parametrize(
    "status",
    [
        ParseJobStatus.QUARANTINED,
        ParseJobStatus.SCANNING,
        ParseJobStatus.PARSING,
        ParseJobStatus.INFECTED,
        ParseJobStatus.FAILED,
    ],
)
def test_unsafe_or_incomplete_jobs_are_never_releaseable(status):
    job = SimpleNamespace(status=status, parsed_storage_key="parsed/document.txt")
    assert is_releaseable(job) is False


def test_ready_job_without_parsed_artifact_is_not_releaseable():
    job = SimpleNamespace(
        status=ParseJobStatus.READY_FOR_REVIEW,
        parsed_storage_key=None,
    )
    assert is_releaseable(job) is False


def test_only_ready_job_with_parsed_artifact_is_releaseable():
    job = SimpleNamespace(
        status=ParseJobStatus.READY_FOR_REVIEW,
        parsed_storage_key="parsed/document.txt",
    )
    assert is_releaseable(job) is True
