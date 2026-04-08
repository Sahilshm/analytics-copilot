FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts

RUN pip install --no-cache-dir -e ".[cloud]"

CMD ["uvicorn", "agentic_analytics.main:app", "--host", "0.0.0.0", "--port", "8080"]
