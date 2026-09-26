

from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis import Redis
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Booking, BookingStatus, User, UserRole
from app.redis_client import (
    booking_rate_limit,
    cache_get,
    cache_set,
    get_redis_dep,
    invalidate_booking_cache,
)
from app.schemas import BookingCreate, BookingOut, BookingPatch

router = APIRouter(prefix="/bookings", tags=["bookings"])

ALLOWED_TRANSITIONS = {
    BookingStatus.pending: {BookingStatus.confirmed, BookingStatus.cancelled},
    BookingStatus.confirmed: {BookingStatus.completed, BookingStatus.cancelled},
    BookingStatus.completed: set(),
    BookingStatus.cancelled: set(),
}


def get_visible_booking(booking_id: int, user: User, db: Session) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="booking not found")
    if user.role == UserRole.customer and booking.customer_id != user.id:
        # 404 on purpose: do not leak that someone else's booking exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="booking not found")
    if user.role == UserRole.provider and booking.provider_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="booking not found")
    return booking


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    r: Redis = Depends(get_redis_dep),
):
    if user.role != UserRole.customer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="only customers book slots")
    booking_rate_limit(user, r)
    provider = db.get(User, body.provider_id)
    if provider is None or provider.role != UserRole.provider:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown provider")
    if body.end_time <= body.start_time:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time"
        )
    booking = Booking(
        customer_id=user.id,
        provider_id=provider.id,
        start_time=body.start_time.replace(tzinfo=None),
        end_time=body.end_time.replace(tzinfo=None),
        status=BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    invalidate_booking_cache(r)
    return booking


@router.get("", response_model=list[BookingOut])
def list_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    r: Redis = Depends(get_redis_dep),
):
    cache_key = f"cache:bookings:{user.role.value}:{user.id}"
    cached = cache_get(r, cache_key)
    if cached is not None:
        return cached
    # ownership scoping happens here, in the query itself - never return-all then filter
    query = db.query(Booking)
    if user.role == UserRole.customer:
        query = query.filter(Booking.customer_id == user.id)
    elif user.role == UserRole.provider:
        query = query.filter(Booking.provider_id == user.id)
    bookings = query.order_by(Booking.created_at.desc()).all()
    payload = [BookingOut.model_validate(b).model_dump(mode="json") for b in bookings]
    cache_set(r, cache_key, payload)
    return payload


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_visible_booking(booking_id, user, db)


@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking_status(
    booking_id: int,
    body: BookingPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    r: Redis = Depends(get_redis_dep),
):
    booking = get_visible_booking(booking_id, user, db)
    if user.role == UserRole.provider and body.status not in {
        BookingStatus.confirmed,
        BookingStatus.completed,
    }:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="providers confirm or complete bookings"
        )
    if user.role == UserRole.customer and body.status != BookingStatus.cancelled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="customers can only cancel")
    if body.status not in ALLOWED_TRANSITIONS[booking.status]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"cannot move booking from {booking.status.value} to {body.status.value}",
        )
    booking.status = body.status
    db.commit()
    db.refresh(booking)
    invalidate_booking_cache(r)
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    r: Redis = Depends(get_redis_dep),
):
    booking = get_visible_booking(booking_id, user, db)
    if user.role == UserRole.customer and booking.status != BookingStatus.pending:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="only pending bookings can be deleted"
        )
    if user.role == UserRole.provider:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="providers cannot delete bookings")
    db.delete(booking)
    db.commit()
    invalidate_booking_cache(r)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
