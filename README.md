# Oura Dashboard

[![CI](https://github.com/MaximeMichaud/oura-dashboard/workflows/CI/badge.svg)](https://github.com/MaximeMichaud/oura-dashboard/actions?query=workflow%3ACI)

Unified dashboard for your [Oura Ring](https://ouraring.com) data - sleep, readiness, activity, stress, and more.

Built with **[Oura API v2](https://cloud.ouraring.com/v2/docs)**, **PostgreSQL 18**, **Grafana 13**, and a Python ingestion service (optional profile) that syncs automatically every 30 minutes.

## Stack

- **Oura API v2** - personal health data
- **PostgreSQL 18** - persistent storage (22 tables + 1 materialized view, auto-migrated)
- **Grafana 13** - 8 pre-provisioned dashboards (no setup required)
- **Python 3.14** - ingestion service with incremental sync, retry logic, and CLI flags

## Prerequisites

- Docker Compose v2+
- Optional: an Oura Ring with data
- Optional: an Oura API connection. Existing legacy bearer tokens still work, and new connections should use OAuth.

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/MaximeMichaud/oura-dashboard.git
cd oura-dashboard
cp .env.example .env
```

### 2. Start (simple mode, no token required)

```bash
docker compose up -d --build
```

This starts PostgreSQL, Grafana, and Streamlit. Streamlit works in PostgreSQL/demo mode even without Oura credentials. Grafana, however, has no demo mode: it reads real data from PostgreSQL, so its dashboards stay empty until you connect an Oura account and start the ingestion profile (step 3). To just explore the UI without an Oura account, open Streamlit at [http://localhost:8501](http://localhost:8501).

### 3. Optional: connect Oura (real synced data)

Existing users can keep using `OURA_TOKEN` in `.env`. New Oura API connections should use OAuth.

Create an Oura API application at [cloud.ouraring.com/oauth/applications](https://cloud.ouraring.com/oauth/applications):

| Field | Suggested value |
|---|---|
| Display Name | `Oura Dashboard Local` |
| Description | `Personal local dashboard for my own Oura data.` |
| Contact Email | Your Oura email |
| Website | Your project or profile URL, for example this repository URL |
| Privacy Policy | Your project or profile URL |
| Terms of Service | Your project or profile URL |
| Redirect URIs | `http://localhost:8765/callback` |

Select the scopes the setup helper requests by default:

```text
personal daily heartrate tag workout session spo2 ring_configuration stress heart_health
```

The scopes you grant on the Oura application must include every scope the helper requests, otherwise authorization fails. To request fewer, set `OURA_OAUTH_SCOPES` to your reduced list and grant exactly those.

Then run the local OAuth setup helper from the repository root:

```bash
make oauth-setup
```

The helper prints an Oura authorization URL, waits on `http://localhost:8765/callback` (bound to localhost only), exchanges the callback code, tests the API, and writes OAuth values to `.env` without removing `OURA_TOKEN`.

Oura refresh tokens are single-use. After the first automatic refresh, ingestion stores the replacement token encrypted
in PostgreSQL using `pgcrypto` and the OAuth client secret. Values in `.env` remain the bootstrap and recovery source;
rotated tokens are never written back to the repository or stored as plaintext in the database. In PostgreSQL mode,
ingestion is the only process allowed to rotate this token, preventing Streamlit from consuming the same token during a
temporary database outage.

If you are not using Docker for setup, install the ingestion dependencies first, then run the helper:

```bash
pip install -r ingestion/requirements.txt
PYTHONPATH=ingestion python -m oura_ingest.cli --oauth-setup
```

Start ingestion with:

```bash
docker compose --profile ingestion up -d --build
```

The ingestion service will start syncing your data immediately (full history from 2020 by default). Initial import can take several minutes for multi-year history.

### 4. Open dashboards

Navigate to [http://localhost:3000](http://localhost:3000) - no login required.
Streamlit is available at [http://localhost:8501](http://localhost:8501).

8 dashboards are available:

| Dashboard | Content |
|---|---|
| **Overview** | Sleep score, readiness, steps, stress, resilience, weekly trends, HRV vs readiness correlation |
| **Sleep** | Sleep phases, HR/HRV intra-night, optimal bedtime, 90-day trends |
| **Readiness** | Score, temperature, contributors |
| **Activity** | Steps, calories, MET, breakdown, target vs actual |
| **Body** | SpO2, stress vs recovery, resilience, cardiovascular age, VO2 Max |
| **Heart Rate** | Heart rate samples, source distribution, and daily ranges |
| **Context** | Sessions, legacy and enhanced tags, and rest mode periods |
| **Ring** | Battery history, ring configuration, firmware, and a profile without email |

## Configuration

All settings are in `.env`:

| Variable | Default | Description |
|---|---|---|
| `OURA_TOKEN` | empty | Legacy Oura bearer token. Supported for existing users. |
| `OURA_CLIENT_ID` | empty | OAuth application client ID. |
| `OURA_CLIENT_SECRET` | empty | OAuth application client secret. |
| `OURA_REFRESH_TOKEN` | empty | OAuth refresh token generated by `--oauth-setup`. |
| `OURA_ACCESS_TOKEN` | empty | Optional cached OAuth access token. |
| `OURA_ACCESS_TOKEN_EXPIRES_AT` | empty | Optional access token expiry as Unix epoch seconds. |
| `OURA_REDIRECT_URI` | `http://localhost:8765/callback` | OAuth redirect URI registered in the Oura application. |
| `OURA_OAUTH_SCOPES` | see `.env.example` | OAuth scopes requested by the local setup helper. |
| `HISTORY_START_DATE` | `2020-01-01` | Start date for initial import |
| `USER_TIMEZONE` | `America/Toronto` | Local timezone used for API date boundaries and Streamlit ranges |
| `SYNC_INTERVAL_MINUTES` | `30` | Sync frequency |
| `OVERLAP_DAYS` | `8` | Days of overlap for incremental sync, covering Ring 4 and Gen3 offline storage |
| `TIMESERIES_HISTORY_DAYS` | `90` | Initial history imported for heart rate and battery time series |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `BIND_ADDRESS` | `127.0.0.1` | Host interface used by Grafana and Streamlit |
| `GRAFANA_PORT` | `3000` | Grafana port |
| `STREAMLIT_PORT` | `8501` | Streamlit port |
| `GF_ADMIN_USER` | `admin` | Grafana admin username |
| `GF_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `GRAFANA_DB_PASSWORD` | `oura_grafana` | Password for Grafana's dedicated read-only PostgreSQL role |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host (inside Docker network) |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `oura` | PostgreSQL database name |
| `POSTGRES_USER` | `oura` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `oura` | PostgreSQL password |

## Makefile Commands

```bash
make up        # docker compose up -d --build (simple mode)
make up-full   # docker compose --profile ingestion up -d --build
make down      # docker compose down
make logs      # docker compose logs -f
make status    # show service status + last sync per endpoint
make psql      # open psql shell to the database
make migrate   # apply the idempotent schema to an existing database volume
```

## UI Validation

The headless Playwright validators capture the provisioned dashboards and Streamlit pages at desktop and mobile
sizes. Screenshots are written to `/tmp`.

```bash
npm install --prefix scripts
node scripts/validate-dashboards.mjs
node scripts/validate-streamlit.mjs
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
| `heartrate` | `heartrate` | `timestamp` |
| `ring_battery_level` | `ring_battery_level` | `timestamp` |
| `ring_configuration` | `ring_configuration` | `id` |
| `session` | `session` | `id` |
| `tag` | `tag` | `id` |
| `enhanced_tag` | `enhanced_tag` | `id` |
| `rest_mode_period` | `rest_mode_period` | `id` |
| `personal_info` | `personal_info` | `id` |

Heart rate and battery imports are split into requests of at most 30 days, as required by the Oura API. The initial
depth defaults to 90 days and remains configurable. `personal_info` deliberately excludes the email field.
`rest_mode_period` is fully refetched on every sync so an open period can receive its eventual end date.

Oura features such as Lab Uploads, Locate, metabolic lab results, meals, and GPS routes are not exposed by a public
read endpoint in the current [OpenAPI 1.35 specification](https://cloud.ouraring.com/v2/static/json/openapi-1.35.json).

## Troubleshooting

| Issue | Fix |
|---|---|
| Dashboard not updating | Hard refresh (Ctrl+Shift+R) or `docker compose down && docker volume rm oura_grafana-storage && make up` |
| No real Oura data visible | Set `OURA_TOKEN` and start with `docker compose --profile ingestion up -d --build` |
| No OAuth token yet | Run `make oauth-setup`, then recreate ingestion with `docker compose --profile ingestion up -d` (a plain `restart` does not reload `.env`) |
| Legacy token expired | Use OAuth setup, or update `OURA_TOKEN` if you still have a valid legacy token, then `docker compose --profile ingestion up -d` |
| "No data" on panels | Check `make status` - if sync_log is empty, the initial import is still running |
| PostgreSQL connection refused | Wait for the healthcheck - Postgres can take a few seconds to start |
| Postgres container stays unhealthy after a major version bump | A new PostgreSQL major cannot reuse an older version's data volume. Dump and restore manually, or reset with `docker compose down -v && make up-full` to re-import |
| Ingestion stuck | Check `docker compose logs ingestion` for error details |
| Nested `_stcore` 404s on Streamlit subpages | This is a [confirmed Streamlit multipage bug](https://github.com/streamlit/streamlit/issues/7074). Streamlit also calls the valid root endpoints; verify `/_stcore/health` returns HTTP 200. |

## Reset

```bash
docker compose down -v   # removes all data volumes
make up-full             # fresh start, re-imports from HISTORY_START_DATE
```
