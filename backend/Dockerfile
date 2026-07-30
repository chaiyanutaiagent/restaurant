FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmagic1 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system app \
    && adduser --system --ingroup app --home /app --no-create-home app

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app

RUN mkdir -p /app/uploads /app/logs \
    && chown -R app:app /app/uploads /app/logs

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
