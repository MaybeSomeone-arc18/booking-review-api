from tests.conftest import login, make_booking


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_customer_sees_own_booking(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    r = client.get(f"/bookings/{booking['id']}", headers=world["c1h"])
    assert r.status_code == 200
    listed = client.get("/bookings", headers=world["c1h"]).json()
    assert [b["id"] for b in listed] == [booking["id"]]


def test_customer_cannot_see_others_booking(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    assert client.get(f"/bookings/{booking['id']}", headers=world["c2h"]).status_code == 404
    assert client.get("/bookings", headers=world["c2h"]).json() == []


def test_provider_sees_own_bookings(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    r = client.get(f"/bookings/{booking['id']}", headers=world["p1h"])
    assert r.status_code == 200


def test_provider_cannot_see_other_providers_bookings(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    assert client.get(f"/bookings/{booking['id']}", headers=world["p2h"]).status_code == 404
    assert client.get("/bookings", headers=world["p2h"]).json() == []


def test_completed_booking_is_reviewable(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "confirmed"}, headers=world["p1h"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "completed"}, headers=world["p1h"])
    r = client.post(
        f"/bookings/{booking['id']}/review",
        json={"rating": 5, "text": "great"},
        headers=world["c1h"],
    )
    assert r.status_code == 201
    assert r.json()["rating"] == 5


def test_pending_booking_is_not_reviewable(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    r = client.post(
        f"/bookings/{booking['id']}/review",
        json={"rating": 5, "text": "too early"},
        headers=world["c1h"],
    )
    assert r.status_code == 400


def test_no_duplicate_review_on_same_booking(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "confirmed"}, headers=world["p1h"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "completed"}, headers=world["p1h"])
    first = client.post(
        f"/bookings/{booking['id']}/review",
        json={"rating": 5, "text": "great"},
        headers=world["c1h"],
    )
    assert first.status_code == 201
    second = client.post(
        f"/bookings/{booking['id']}/review",
        json={"rating": 1, "text": "changed my mind"},
        headers=world["c1h"],
    )
    assert second.status_code == 409


def test_summary_job_flow(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "confirmed"}, headers=world["p1h"])
    client.patch(f"/bookings/{booking['id']}", json={"status": "completed"}, headers=world["p1h"])
    client.post(
        f"/bookings/{booking['id']}/review",
        json={"rating": 4, "text": "good"},
        headers=world["c1h"],
    )
    r = client.post("/reviews/summarize", json={}, headers=world["p1h"])
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    job = client.get(f"/reviews/summarize/{job_id}", headers=world["p1h"]).json()
    assert job["status"] == "queued"
    # providers cannot read another provider's job
    assert client.get(f"/reviews/summarize/{job_id}", headers=world["p2h"]).status_code == 404


def test_admin_sees_all_bookings(client, world):
    from app.db import SessionLocal
    from app.models import User, UserRole
    from app.security import hash_password

    make_booking(client, world["c1h"], world["p1"]["id"])
    make_booking(client, world["c2h"], world["p2"]["id"], start="2026-10-02T10:00:00")
    db = SessionLocal()
    db.add(
        User(
            email="admin@test.com",
            hashed_password=hash_password("password123"),
            role=UserRole.admin,
        )
    )
    db.commit()
    db.close()
    admin_headers = login(client, "admin@test.com")
    assert len(client.get("/bookings", headers=admin_headers).json()) == 2


def test_register_cannot_create_admin(client):
    r = client.post(
        "/auth/register",
        json={"email": "sneaky@test.com", "password": "password123", "role": "admin"},
    )
    assert r.status_code == 403


def test_invalid_status_transition_rejected(client, world):
    booking = make_booking(client, world["c1h"], world["p1"]["id"])
    r = client.patch(
        f"/bookings/{booking['id']}", json={"status": "completed"}, headers=world["p1h"]
    )
    assert r.status_code == 400


def test_summary_returns_503_when_queue_is_down(client, world):
    import redis as redis_lib

    from app.main import app
    from app.redis_client import get_redis_dep

    class DeadRedis:
        def __getattr__(self, name):
            raise redis_lib.RedisError("down")

    app.dependency_overrides[get_redis_dep] = lambda: DeadRedis()
    try:
        r = client.post("/reviews/summarize", json={}, headers=world["p1h"])
        assert r.status_code == 503
    finally:
        app.dependency_overrides.pop(get_redis_dep)


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Service Booking" in r.text
