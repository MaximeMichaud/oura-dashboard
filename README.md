# Oura Dashboard

[![CI](https://github.com/MaximeMichaud/oura-dashboard/workflows/CI/badge.svg)](https://github.com/MaximeMichaud/oura-dashboard/actions?query=workflow%3ACI)

Unified dashboard for your [Oura Ring](https://ouraring.com) data - sleep, readiness, activity, stress, and more.

Built with **[Oura API v2](https://cloud.ouraring.com/v2/docs)**, **PostgreSQL 16**, **Grafana 12**, and a Python ingestion service that syncs automatically every 30 minutes.

## Stack

- **Oura API v2** - personal health data
- **PostgreSQL 16** - persistent storage (12 tables, auto-initialized)
- **Grafana 12** - 5 pre-provisioned dashboards (no setup required)
- **Python 3.14** - ingestion service with incremental sync and retry logic

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

The ingestion service will start syncing your data immediately (full history from 2020 by default).

### 4. Open Grafana

Navigate to [http://localhost:3000](http://localhost:3000) - no login required.

5 dashboards are available:

| Dashboard | Content |
|---|---|
| **Overview** | Sleep score, readiness, steps, stress, resilience, SpO2 |
| **Sleep** | Sleep phases, HR/HRV intra-night, 90-day trends |
| **Readiness** | Score, temperature, contributors |
| **Activity** | Steps, calories, MET, breakdown |
| **Body** | SpO2, stress vs recovery, resilience, cardiovascular age |

## Configuration

All settings are in `.env`:

| Variable | Default | Description |
|---|---|---|
| `OURA_TOKEN` | (required) | Oura personal access token |
| `HISTORY_START_DATE` | `2020-01-01` | Start date for initial import |
| `SYNC_INTERVAL_MINUTES` | `30` | Sync frequency |
| `OVERLAP_DAYS` | `2` | Days of overlap for incremental sync |
| `GRAFANA_PORT` | `3000` | Grafana port |
| `GF_ADMIN_USER` | `admin` | Grafana admin username |
| `GF_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `oura` | PostgreSQL database name |
| `POSTGRES_USER` | `oura` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `oura` | PostgreSQL password |

## Commands

```bash
docker compose up -d --build   # start everything
docker compose down            # stop
docker compose logs -f         # follow logs
```
