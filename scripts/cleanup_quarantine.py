from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.core.dependencies import get_security_session_factory  # noqa: E402
from app.documents.jobs import ParseJob, ParseJobStatus  # noqa: E402
from app.documents.storage import DocumentStorage  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = get_config()
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=config["parser"]["quarantine_retention_days"]
    )
    storage = DocumentStorage(Path(config["storage"]["root"]))
    removed = 0
    with get_security_session_factory()() as session:
        statement = select(ParseJob).where(
            ParseJob.status.in_(
                [
                    ParseJobStatus.READY_FOR_REVIEW,
                    ParseJobStatus.INFECTED,
                    ParseJobStatus.FAILED,
                ]
            ),
            ParseJob.completed_at.is_not(None),
            ParseJob.completed_at < cutoff,
        )
        for job in session.scalars(statement):
            path = storage.resolve(job.quarantine_storage_key)
            if args.apply:
                path.unlink(missing_ok=True)
            removed += 1
    mode = "removed" if args.apply else "eligible"
    print(f"quarantine objects {mode}: {removed}")


if __name__ == "__main__":
    main()
