# Oura Dashboard

[![CI](https://github.com/MaximeMichaud/oura-dashboard/workflows/CI/badge.svg)](https://github.com/MaximeMichaud/oura-dashboard/actions?query=workflow%3ACI)

Unified dashboard for your [Oura Ring](https://ouraring.com) data - sleep, readiness, activity, stress, and more.

Built with **[Oura API v2](https://cloud.ouraring.com/v2/docs)**, **PostgreSQL 16**, **Grafana 12**, and a Python ingestion service that syncs automatically every 30 minutes.

## Stack

- **Oura API v2** - personal health data
- **PostgreSQL 16** - persistent storage (13 tables + 1 materialized view, auto-initialized)
- **Grafana 12.3.3** - 5 pre-provisioned dashboards (no setup required)
- **Python 3.14** - ingestion service with incremental sync, retry logic, and CLI flags

## Prerequisites

- Docker Compose v2+
- An Oura Ring with data
- A personal access token from [cloud.ouraring.com](https://cloud.ouraring.com/personal-access-tokens)

## Quick Start

### 1. Get your Oura API token

Generate a personal access token at [cloud.ouraring.com/personal-access-tokens](https://cloud.ouraring.com/personal-access-tokens).

### 2. Clone and configure

```bash
git clone https://github.com/MaximeMichaud/oura-dashboard.git
cd oura-dashboard
cp .env.example .env
```

Edit `.env` and set your token:

```env
OURA_TOKEN=your_token_here
```

### 3. Start

```bash
docker compose up -d --build
```

The ingestion service will start syncing your data immediately (full history from 2020 by default). Initial import can take several minutes for multi-year history.

### 4. Open Grafana

Navigate to [http://localhost:3000](http://localhost:3000) - no login required.

5 dashboards are available:

| Dashboard | Content |
|---|---|
| **Overview** | Sleep score, readiness, steps, stress, resilience, weekly trends, HRV vs readiness correlation |
| **Sleep** | Sleep phases, HR/HRV intra-night, optimal bedtime, 90-day trends |
| **Readiness** | Score, temperature, contributors |
| **Activity** | Steps, calories, MET, breakdown, target vs actual |
| **Body** | SpO2, stress vs recovery, resilience, cardiovascular age, VO2 Max |

## Configuration

All settings are in `.env`:

| Variable | Default | Description |
|---|---|---|
| `OURA_TOKEN` | (required) | Oura personal access token |
| `HISTORY_START_DATE` | `2020-01-01` | Start date for initial import |
| `SYNC_INTERVAL_MINUTES` | `30` | Sync frequency |
| `OVERLAP_DAYS` | `2` | Days of overlap for incremental sync |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `GRAFANA_PORT` | `3000` | Grafana port |
| `GF_ADMIN_USER` | `admin` | Grafana admin username |
| `GF_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host (inside Docker network) |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `oura` | PostgreSQL database name |
| `POSTGRES_USER` | `oura` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `oura` | PostgreSQL password |

## Makefile Commands

```bash
make up        # docker compose up -d --build
make down      # docker compose down
make logs      # docker compose logs -f
make status    # show service status + last sync per endpoint
make psql      # open psql shell to the database
```

## CLI Flags

The ingestion service supports CLI flags:

```bash
# List all available endpoints
python -m oura_ingest.cli --list-endpoints

# Sync once and exit (no scheduler)
python -m oura_ingest.cli --once

# Sync a specific endpoint only
python -m oura_ingest.cli --once --endpoint daily_sleep
```

## API Endpoints

| Oura API Endpoint | PostgreSQL Table | Primary Key |
|---|---|---|
| `sleep` | `sleep` | `id` (UUID) |
| `daily_sleep` | `daily_sleep` | `day` |
| `daily_readiness` | `daily_readiness` | `day` |
| `daily_activity` | `daily_activity` | `day` |
| `daily_spo2` | `daily_spo2` | `day` |
| `daily_stress` | `daily_stress` | `day` |
| `daily_resilience` | `daily_resilience` | `day` |
| `daily_cardiovascular_age` | `daily_cardiovascular_age` | `day` |
| `vO2_max` | `daily_vo2_max` | `day` |
| `workout` | `workout` | `id` |
| `sleep_time` | `sleep_time` | `id` |

## Troubleshooting

| Issue | Fix |
|---|---|
| Dashboard not updating | Hard refresh (Ctrl+Shift+R) or `docker compose down && docker volume rm oura_grafana-storage && make up` |
| Token expired | Get a new token, update `.env`, then `docker compose restart ingestion` |
| "No data" on panels | Check `make status` - if sync_log is empty, the initial import is still running |
| PostgreSQL connection refused | Wait for the healthcheck - Postgres can take a few seconds to start |
| Ingestion stuck | Check `docker compose logs ingestion` for error details |

## Reset

```bash
docker compose down -v   # removes all data volumes
make up                  # fresh start, re-imports from HISTORY_START_DATE
```
