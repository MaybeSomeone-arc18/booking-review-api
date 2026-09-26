import os

# point the app at sqlite + fake redis before importing it
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ["JWT_SECRET"] = "test-secret"

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.redis_client import get_redis_dep


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    fake = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis_dep] = lambda: fake
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email, role):
    r = client.post(
        "/auth/register", json={"email": email, "password": "password123", "role": role}
    )
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_booking(client, customer_headers, provider_id, start="2026-10-01T10:00:00"):
    end = start[:11] + "11:00:00"
    r = client.post(
        "/bookings",
        json={"provider_id": provider_id, "start_time": start, "end_time": end},
        headers=customer_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def world(client):
    provider1 = register(client, "p1@test.com", "provider")
    provider2 = register(client, "p2@test.com", "provider")
    customer1 = register(client, "c1@test.com", "customer")
    customer2 = register(client, "c2@test.com", "customer")
    return {
        "p1": provider1,
        "p2": provider2,
        "c1": customer1,
        "c2": customer2,
        "p1h": login(client, "p1@test.com"),
        "p2h": login(client, "p2@test.com"),
        "c1h": login(client, "c1@test.com"),
        "c2h": login(client, "c2@test.com"),
    }
