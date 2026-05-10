# Project: Personal Finance Tracker API
Beginner level
REST API quản lý thu chi cá nhân. Scope nhỏ nhưng đủ để thực hành đầy đủ CRUD, auth, và deploy lần đầu.
## Tech stack
- `FastAPI routing`
- `SQLAlchemy` + `Alembic`
- `JWT` auth
- `Pydantic` schemas
- `Docker` Compose
- `pytest`

**Feature:**
- CRUD transactions, categories, budget targets — Pydantic validate input, SQLAlchemy async ORM
- Register/login với JWT — refresh token stored in Redis
- Monthly summary endpoint — raw SQL aggregation qua SQLAlchemy text()
- Alembic migration từ đầu + seed script — thực hành schema evolution
- Docker Compose: app + postgres + redis chạy local 1 lệnh
- pytest: unit test service layer + integration test endpoints qua TestClient
- Deploy lên Railway/Fly.io với GitHub Actions (push-to-deploy)