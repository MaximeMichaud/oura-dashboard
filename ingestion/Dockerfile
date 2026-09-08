FROM python:3.14-alpine

# hadolint ignore=DL3017
RUN apk upgrade --no-cache && apk add --no-cache libpq

WORKDIR /app
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps \
    && rm -rf /usr/local/lib/python3*/site-packages/pip \
              /usr/local/lib/python3*/site-packages/pip-*.dist-info \
              /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.*

COPY oura_ingest/ oura_ingest/

RUN addgroup -g 10001 -S appgroup && adduser -u 10001 -S appuser -G appgroup
USER 10001:10001

CMD ["python", "-m", "oura_ingest.cli"]
