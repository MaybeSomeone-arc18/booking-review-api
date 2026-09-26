# Service Booking & Review API

![ci](https://github.com/MaybeSomeone-arc18/booking-review-api/actions/workflows/ci.yml/badge.svg)

A small FastAPI service that models the core of a service booking and review
platform: providers offer time slots, customers book them, and each completed
booking can be reviewed once.

Built as a take-home assessment. Everything runs with one command.

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL · Alembic · Redis · PyJWT · pytest · ruff · Docker Compose

## Run it

```bash
docker compose up --build
```

Then open **http://localhost:8000/docs** - interactive Swagger UI for every endpoint.

The API container runs migrations and seeds demo data on boot, so the first
`docker compose up` gives you a working system with data in it.

### Demo accounts

| Role     | Email              | Password  |
|----------|--------------------|-----------|
| admin    | admin@demo.com     | demo1234  |
| provider | provider@demo.com  | demo1234  |
| provider | provider2@demo.com | demo1234  |
| customer | customer@demo.com  | demo1234  |
| customer | customer2@demo.com | demo1234  |

Login at `POST /auth/login`, then use the token as a Bearer token (the Swagger
"Authorize" button works).

## Endpoints

| Method | Path                            | Who                         |
|--------|---------------------------------|-----------------------------|
| POST   | /auth/register                  | anyone (customer/provider)  |
| POST   | /auth/login                     | anyone                      |
| GET    | /health                         | anyone                      |
| POST   | /bookings                       | customer                    |
| GET    | /bookings                       | any role (scoped)           |
| GET    | /bookings/{id}                  | owner / admin               |
| PATCH  | /bookings/{id}                  | owner / admin (status flow) |
| DELETE | /bookings/{id}                  | customer (pending) / admin  |
| POST   | /bookings/{id}/review           | customer (completed only)   |
| GET    | /bookings/{id}/review           | owner / admin               |
| POST   | /reviews/summarize              | provider / admin -> 202     |
| GET    | /reviews/summarize/{job_id}     | owning provider / admin     |

## How access control works

Authentication is a JWT bearer token. Authorization happens in two places:

1. **Role checks at the route** - e.g. only customers can create bookings.
2. **Ownership filters inside the query** - a customer's `GET /bookings` is
   `WHERE customer_id = me`, a provider's is `WHERE provider_id = me`. Admin
   sees everything. Single-object reads return 404 (not 403) for other
   people's data so the API does not leak that a booking exists.

## What Redis does

- **Cache**: `GET /bookings` (the hot read) is cached per user for 60s and
  invalidated on every booking write.
- **Queue**: `POST /reviews/summarize` pushes a job onto a Redis list and
  returns 202. The `worker` container pops jobs and writes a stub summary back
  to the job key. Poll `GET /reviews/summarize/{job_id}` for the result.
- **Rate limit**: fixed-window limiter on booking creation.

Every Redis use fails open with a logged warning - a Redis outage degrades the
API instead of killing it.

## Development

```bash
pip install -r requirements-dev.txt
alembic upgrade head        # needs DATABASE_URL pointing at Postgres
pytest                      # tests run on SQLite + fakeredis locally, Postgres in CI
ruff check .
```

CI runs ruff, applies the Alembic migration against real Postgres, then runs
the test suite on that Postgres.

## Design decisions and limitations

See [DESIGN.md](DESIGN.md) for the written note: schema tradeoffs, how the
RBAC evolves for a fourth role or nested organisations, and what is missing
for production.
