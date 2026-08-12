FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ISSUEPILOT_DATABASE_PATH=/data/issuepilot.db

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "issuepilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
