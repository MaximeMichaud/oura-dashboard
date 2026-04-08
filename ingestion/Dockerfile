FROM python:3.14-alpine

RUN apk add --no-cache libpq

WORKDIR /app
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY oura_ingest/ oura_ingest/

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

CMD ["python", "-m", "oura_ingest.cli"]
