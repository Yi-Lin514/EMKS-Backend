FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY app/ ./app/

EXPOSE 8000

CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
