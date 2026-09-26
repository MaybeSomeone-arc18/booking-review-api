"""Stub worker for the review summarisation job.

Pops jobs off the Redis queue, computes a placeholder summary from the
provider's reviews and stores it back on the job key. No real LLM call -
the queue contract is what matters here.
"""

import json
import logging
import time

from app.db import SessionLocal
from app.models import Booking, Review
from app.redis_client import QUEUE_KEY, get_redis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")


def process(job: dict) -> str:
    db = SessionLocal()
    try:
        reviews = (
            db.query(Review)
            .join(Booking, Review.booking_id == Booking.id)
            .filter(Booking.provider_id == job["provider_id"])
            .all()
        )
        if not reviews:
            return "No reviews yet for this provider."
        avg = sum(r.rating for r in reviews) / len(reviews)
        return f"{len(reviews)} reviews, average rating {avg:.1f}/5. (stub summary)"
    finally:
        db.close()


def main() -> None:
    r = get_redis()
    log.info("worker listening on %s", QUEUE_KEY)
    while True:
        item = r.blpop(QUEUE_KEY, timeout=5)
        if item is None:
            continue
        job = json.loads(item[1])
        job_id = job["job_id"]
        r.hset(f"job:{job_id}", "status", "running")
        try:
            result = process(job)
            r.hset(f"job:{job_id}", mapping={"status": "done", "result": result})
            log.info("job %s done", job_id)
        except Exception:
            log.exception("job %s failed", job_id)
            r.hset(f"job:{job_id}", "status", "failed")
        time.sleep(0.1)


if __name__ == "__main__":
    main()
