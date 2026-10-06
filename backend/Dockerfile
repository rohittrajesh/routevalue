FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project


FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src /app/src

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

CMD ["uvicorn", "routevalue.main:app", "--host", "0.0.0.0", "--port", "8000"]