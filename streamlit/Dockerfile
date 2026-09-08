FROM python:3.14-alpine

# hadolint ignore=DL3017
RUN apk upgrade --no-cache && apk add --no-cache libpq

WORKDIR /app
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps gcc g++ musl-dev postgresql-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps \
    && rm -rf /usr/local/lib/python3*/site-packages/pip \
              /usr/local/lib/python3*/site-packages/pip-*.dist-info \
              /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.*

COPY . .

RUN addgroup -g 10001 -S appgroup && adduser -u 10001 -S appuser -G appgroup
USER 10001:10001

EXPOSE 8501
HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
