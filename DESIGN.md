# Design note

## Why this schema shape

Three tables: users, bookings, reviews. That is it.

Users carries a role column (admin, provider, customer) as a plain enum, not a
separate roles table with a join. I thought about normalising roles out, but
with three fixed roles a lookup table buys nothing and makes every query join
for no reason. If roles ever become dynamic, that decision changes.

Bookings holds customer_id and provider_id as plain foreign keys to users. I
did not split customers and providers into their own tables because a booking
needs the same things from both sides. The tradeoff: if providers later need
profile data customers do not, users grows columns that are null for most
rows. I would split then, not now.

Reviews is a separate table with a unique constraint on booking_id. One review
per booking is a business rule, so I enforced it in the database instead of
hoping the application layer remembers. The tradeoff is that editing or
re-reviewing needs an update flow that does not exist yet.

Timestamps are naive UTC. Fine for one region, wrong for a global product.

## What breaks at a fourth role, or nested orgs

My RBAC is a role check at the route plus ownership filters in the query. It
works because three roles have disjoint, simple rules. A fourth role that
overlaps (say a support agent who can read but not write) breaks the
route-level enum pattern: I would move to permission-based checks, where a
role maps to a set of permissions and routes test permissions, not roles.

Nested organisations break the ownership model itself. "Your bookings" stops
being a user-id comparison and becomes an org-scoped query. That is a bigger
change: organisations as a table, membership in the middle, and every query
scoped through it. I would not pretend the current shape survives that.

## What is missing for production

- Secrets are env vars in compose. Production needs real secret management
  and rotated JWT keys.
- Password hashing is stdlib PBKDF2. Fine here; I would move to argon2.
- No TLS termination, no refresh tokens, just a 24-hour access token.
- Cache invalidation is a blunt prefix scan. Fine at this size, lazy at scale.
- The summary job has no retries or dead-letter queue. If the worker dies
  mid-job, the job is lost.
- No structured logging, metrics, or tracing. That is the first thing I would
  add, because you cannot fix what you cannot see.
- No backups, no tuned connection pooling, no load testing.
