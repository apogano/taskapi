FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN chmod -R a+rX /app/app /app/migrations && chmod a+r /app/alembic.ini

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home appuser
USER appuser

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
    
