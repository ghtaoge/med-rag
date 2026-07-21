from __future__ import annotations


class ParseQueue:
    def __init__(self, queue):
        self.queue = queue

    def submit(self, parse_job_id: str) -> str:
        job = self.queue.enqueue(
            "app.documents.worker.process_parse_job",
            parse_job_id,
            job_timeout=660,
            result_ttl=86400,
            failure_ttl=604800,
        )
        return job.id
