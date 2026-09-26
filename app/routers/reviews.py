import redis
from fastapi import APIRouter, Depends, HTTPException, status
from redis import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import BookingStatus, Review, User, UserRole
from app.redis_client import enqueue_summary_job, get_job, get_redis_dep
from app.routers.bookings import get_visible_booking
from app.schemas import JobOut, ReviewCreate, ReviewOut, SummarizeRequest

router = APIRouter(tags=["reviews"])


@router.post(
    "/bookings/{booking_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    booking_id: int,
    body: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.customer)),
):
    booking = get_visible_booking(booking_id, user, db)
    if booking.status != BookingStatus.completed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="only completed bookings can be reviewed"
        )
    review = Review(booking_id=booking.id, rating=body.rating, text=body.text)
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="this booking already has a review"
        ) from None
    db.refresh(review)
    return review


@router.get("/bookings/{booking_id}/review", response_model=ReviewOut)
def get_review(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = get_visible_booking(booking_id, user, db)
    if booking.review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no review for this booking")
    return booking.review


@router.post("/reviews/summarize", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def trigger_summary(
    body: SummarizeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.provider, UserRole.admin)),
    r: Redis = Depends(get_redis_dep),
):
    if user.role == UserRole.provider:
        provider_id = user.id
    else:
        if body.provider_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="admins must pass provider_id"
            )
        provider = db.get(User, body.provider_id)
        if provider is None or provider.role != UserRole.provider:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown provider")
        provider_id = provider.id
    try:
        job_id = enqueue_summary_job(r, provider_id=provider_id, requested_by=user.id)
    except redis.RedisError:
        # the queue is the one Redis use that cannot fail open - a queue with
        # no store cannot pretend it accepted the job
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="job queue unavailable"
        ) from None
    return JobOut(job_id=job_id, status="queued")


@router.get("/reviews/summarize/{job_id}", response_model=JobOut)
def get_summary_job(
    job_id: str,
    user: User = Depends(require_roles(UserRole.provider, UserRole.admin)),
    r: Redis = Depends(get_redis_dep),
):
    job = get_job(r, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    if user.role == UserRole.provider and int(job["provider_id"]) != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    return JobOut(job_id=job_id, status=job["status"], result=job.get("result") or None)
