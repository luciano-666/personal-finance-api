# =============================================================================
# Stage 1: Builder — cài dependencies với uv
# =============================================================================
FROM python:3.14-slim AS builder

# Pinned version để reproducible builds
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/

# --- Intermediate layer: chỉ cài dependencies, chưa cài project ---
# bind mount uv.lock + pyproject.toml từ root (build context = root)
# Layer này chỉ rebuild khi uv.lock hoặc pyproject.toml thay đổi
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --no-dev

# --- Copy source code rồi cài project ---
COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/
COPY ./backend/app /app/backend/app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev

# =============================================================================
# Stage 2: Runtime — image cuối, không chứa uv
# =============================================================================
FROM python:3.14-slim AS runtime

# Tạo non-root user để chạy app (security best practice)
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app/backend/

# Copy virtual env và source từ builder — uv không được copy sang
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/backend /app/backend

# Copy prestart script (cần thiết cho service prestart trong compose)
COPY --chown=app:app ./backend/scripts /app/backend/scripts
RUN chmod +x /app/backend/scripts/prestart.sh

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend"

USER app

EXPOSE 8000

# prestart service trong compose override CMD này bằng: bash scripts/prestart.sh
# backend service dùng CMD này để start server
CMD ["fastapi", "run", "--workers", "4", "app/main.py"]