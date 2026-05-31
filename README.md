# Personal Finance Tracker API

A REST API for personal finance management — built as a deliberate learning project to practice production-grade backend patterns in Python.

> **Stack:** FastAPI · PostgreSQL · Redis · SQLAlchemy (async) · JWT · Docker · pytest

---

## What this project covers

| Area | Details |
|---|---|
| **CRUD** | Transactions, categories, budgets — with ownership scoping and input validation |
| **Auth** | JWT access tokens + refresh token rotation, Redis-backed blacklist on logout |
| **Analytics** | Monthly income/expense summary with per-category budget tracking |
| **Testing** | Async test suite with savepoint-based transaction rollback for isolation |
| **Infrastructure** | Multi-stage Dockerfile, Docker Compose with PostgreSQL + Redis + Adminer |

---

## Design decisions worth noting

A few patterns here that go beyond the basic tutorial:

**Refresh token rotation with reuse detection**
Every `/login/refresh` call revokes the old token and issues a new one. If a token is reused (sign of theft), *all* sessions for that user are immediately revoked.

**Redis for access token blacklisting, PostgreSQL for refresh token lifecycle**
Access tokens are short-lived and need sub-millisecond blacklist checks on every request — Redis with TTL-based auto-expiry is the right tool. Refresh tokens need persistent storage, audit trails, and relational queries (revoke all by user_id) — PostgreSQL handles that better.

**Timing attack prevention on login**
When a login attempt uses an email that doesn't exist, the server still runs a full password hash verification against a dummy hash. Without this, response time differences would leak whether an email is registered.

**Password hash upgrade on login (bcrypt → Argon2)**
The authenticate function detects legacy bcrypt hashes and transparently upgrades them to Argon2 on successful login — no forced password resets needed.

**Savepoint-based test isolation**
Each test runs inside a nested transaction (savepoint) that rolls back after the test completes. No manual `DELETE` cleanup, no test ordering dependencies, and the schema is only created once per session.

**CRUD layer stays HTTP-free**
CRUD functions accept plain `AsyncSession` and return data or `None`. HTTP status codes and exception raising belong exclusively in route handlers. This keeps the data layer independently testable.

---

## Project structure

```
backend/
├── app/
│   ├── api/
│   │   ├── deps.py          # FastAPI dependencies (auth, DB session)
│   │   └── routes/          # One file per resource
│   │       ├── login.py
│   │       ├── users.py
│   │       ├── transactions.py
│   │       ├── categories.py
│   │       ├── budgets.py
│   │       └── analytics.py
│   ├── alembic/             # Database migrations
│   ├── core/
│   │   ├── config.py        # Pydantic Settings
│   │   ├── db.py
│   │   ├── redis.py
│   │   └── security.py      # JWT, password hashing
│   ├── crud.py              # All database operations
│   ├── models.py            # SQLAlchemy ORM models
│   ├── schemas.py           # Pydantic request/response schemas
│   └── main.py
└── tests/
    ├── api/routes/          # API-layer integration tests
    └── crud/                # CRUD-layer unit tests
```

---

## Running locally

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Clone and configure
git clone <repo-url>
cd <repo>
cp .env.example .env        # fill in required values

# 2. Start all services (DB, Redis, API)
docker compose up

# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
# Adminer (DB viewer) at http://localhost:8080
```

**Running tests:**

```bash
# From the backend/ directory
cd backend
pytest
```

**Seeding sample data:**

```bash
python seed.py    # creates 6 users with 3 months of realistic transaction history
```

---

## API overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/login/access-token` | Login, returns access + refresh token |
| `POST` | `/api/v1/login/refresh` | Rotate refresh token |
| `POST` | `/api/v1/logout` | Blacklist current access token |
| `POST` | `/api/v1/logout/all` | Revoke all sessions |
| `GET` | `/api/v1/users/me` | Current user profile |
| `POST` | `/api/v1/users/signup` | Register |
| `GET` | `/api/v1/transactions/` | List transactions (filterable, paginated) |
| `POST` | `/api/v1/transactions/` | Create transaction |
| `PATCH` | `/api/v1/transactions/{id}` | Update transaction |
| `DELETE` | `/api/v1/transactions/{id}` | Delete transaction |
| `GET/POST/PATCH/DELETE` | `/api/v1/categories/` | Category management |
| `GET/POST/PATCH/DELETE` | `/api/v1/budgets/` | Budget management |
| `GET` | `/api/v1/analytics/summary` | Monthly income/expense summary |

Full interactive documentation available at `/docs` when running locally.

---

## What's intentionally out of scope

This is a learning project with a defined scope. The following were left out deliberately:

- **Email delivery** — password recovery generates a valid token but does not send email (no SMTP configured)
- **Production deployment** — Dockerfile and Compose are production-ready, but CI/CD and cloud deployment are saved for the next project
- **Frontend** — API only

---

## Context

This is the first in a series of portfolio projects, each targeting a higher complexity level. The goal here was to get the fundamentals right: clean separation between layers, proper auth patterns, and a test suite that's actually useful rather than just hitting coverage numbers.

The next project moves into intermediate territory: background task queues, more complex authorization patterns, and a complete CI/CD pipeline with production deployment.