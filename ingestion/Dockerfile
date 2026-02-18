FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oura_ingest/ oura_ingest/

CMD ["python", "-m", "oura_ingest.cli"]
