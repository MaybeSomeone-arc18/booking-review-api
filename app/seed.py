"""Idempotent demo seed: run after migrations so the app has data on first boot."""

from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import Booking, BookingStatus, Review, User, UserRole
from app.security import hash_password

DEMO_PASSWORD = "demo1234"

USERS = [
    ("admin@demo.com", UserRole.admin),
    ("provider@demo.com", UserRole.provider),
    ("provider2@demo.com", UserRole.provider),
    ("customer@demo.com", UserRole.customer),
    ("customer2@demo.com", UserRole.customer),
]


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("seed: users already exist, skipping")
            return
        users = {}
        for email, role in USERS:
            user = User(email=email, hashed_password=hash_password(DEMO_PASSWORD), role=role)
            db.add(user)
            users[email] = user
        db.flush()

        now = datetime.utcnow().replace(microsecond=0)
        b1 = Booking(
            customer_id=users["customer@demo.com"].id,
            provider_id=users["provider@demo.com"].id,
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=2) + timedelta(hours=1),
            status=BookingStatus.completed,
        )
        b2 = Booking(
            customer_id=users["customer@demo.com"].id,
            provider_id=users["provider@demo.com"].id,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
            status=BookingStatus.confirmed,
        )
        b3 = Booking(
            customer_id=users["customer2@demo.com"].id,
            provider_id=users["provider2@demo.com"].id,
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=2, hours=1),
            status=BookingStatus.pending,
        )
        db.add_all([b1, b2, b3])
        db.flush()
        db.add(Review(booking_id=b1.id, rating=5, text="On time and great work."))
        db.commit()
        print("seed: demo data created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
