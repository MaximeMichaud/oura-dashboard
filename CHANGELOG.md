# Changelog

## [0.3.0](https://github.com/MaximeMichaud/oura-dashboard/compare/v0.2.0...v0.3.0) (2026-07-10)

Oura Dashboard 0.3.0 adds first-class OAuth support, eight additional Oura API collections, three new dashboards, persistent token rotation, and full-stack release validation. Legacy personal access tokens remain supported.

### Highlights

* Connect through Oura OAuth while retaining `OURA_TOKEN` as a backwards-compatible fallback ([71949fd](https://github.com/MaximeMichaud/oura-dashboard/commit/71949fd0dde295df0c43ee63badde7c6402bfbe0))
* Explore heart rate, context, and ring data through dedicated Streamlit pages and Grafana dashboards ([f728362](https://github.com/MaximeMichaud/oura-dashboard/commit/f728362138bf09361399ef82167baa41a4daf120), [7f3740f](https://github.com/MaximeMichaud/oura-dashboard/commit/7f3740fb953f8c0f5ae6fa1371724f779d39684b))
* Keep rotated OAuth credentials encrypted and synchronized across restarts ([5f3c24c](https://github.com/MaximeMichaud/oura-dashboard/commit/5f3c24cdc7d77aca686cf9d25d1b5478e797a728))
* Validate the real Docker Compose stack, every Streamlit page, and every Grafana panel in CI ([3cb166c](https://github.com/MaximeMichaud/oura-dashboard/commit/3cb166cdd8af4f834b6979a51c8f6f5f916f8579), [862bd45](https://github.com/MaximeMichaud/oura-dashboard/commit/862bd452f1cffeec0464f9307865b1c91a3233dd))

### Breaking Changes

* **PostgreSQL 18:** PostgreSQL was upgraded from 16 to 18. PostgreSQL 16 data volumes cannot be mounted directly by PostgreSQL 18. Existing installations must use a standard `pg_dump`/`pg_restore` major-version migration or recreate their local volumes and re-import Oura data ([738de8b](https://github.com/MaximeMichaud/oura-dashboard/commit/738de8bdc234de002aaa44999ade29ea7c0f39e2), [6bdea99](https://github.com/MaximeMichaud/oura-dashboard/commit/6bdea99aaebe8a39d9b2d62ea179a5279c0b4861))
* **Local-only ports by default:** Grafana and Streamlit now bind to `127.0.0.1`. Set `BIND_ADDRESS=0.0.0.0` only when LAN access is required and the host is protected by an appropriate firewall ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))

### Upgrade Notes

1. Back up the PostgreSQL database and keep a secure copy of `.env` before updating. Never commit that file.
2. For an existing PostgreSQL 16 installation, migrate with `pg_dump`/`pg_restore`. To discard local database and Grafana state and rebuild everything from Oura instead, run `docker compose down -v` followed by `make up-full`. This reset is destructive.
3. Review `.env.example` for the new OAuth, Grafana database, binding, and synchronization variables. Existing `OURA_TOKEN` configurations continue to work without creating an OAuth application.
4. To use OAuth, register a current Oura application with `http://localhost:8765/callback` as its redirect URI, set `OURA_CLIENT_ID` and `OURA_CLIENT_SECRET`, then run `make oauth-setup`.
5. Start or recreate the complete stack with `make up-full`, then verify services and endpoint cursors with `make status`.

### Features

* Add OAuth authorization, CSRF state validation, local callback handling, refresh support, and an interactive setup command ([71949fd](https://github.com/MaximeMichaud/oura-dashboard/commit/71949fd0dde295df0c43ee63badde7c6402bfbe0))
* Add ingestion for `heartrate`, `ring_battery_level`, `ring_configuration`, `session`, `tag`, `enhanced_tag`, `rest_mode_period`, and `personal_info` ([f728362](https://github.com/MaximeMichaud/oura-dashboard/commit/f728362138bf09361399ef82167baa41a4daf120))
* Add Heart Rate, Context, and Ring views to both Streamlit and Grafana ([7f3740f](https://github.com/MaximeMichaud/oura-dashboard/commit/7f3740fb953f8c0f5ae6fa1371724f779d39684b))
* Add an idempotent migration service that applies schema and Grafana role changes before application services start ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Add PostgreSQL-backed OAuth token persistence so refresh-token rotation survives container recreation ([5f3c24c](https://github.com/MaximeMichaud/oura-dashboard/commit/5f3c24cdc7d77aca686cf9d25d1b5478e797a728))

### Security

* Encrypt persisted OAuth token state with PostgreSQL `pgcrypto` and prevent Grafana from reading it ([5f3c24c](https://github.com/MaximeMichaud/oura-dashboard/commit/5f3c24cdc7d77aca686cf9d25d1b5478e797a728), [51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Use a dedicated read-only PostgreSQL role for Grafana instead of the ingestion account ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Restrict published service ports to localhost by default and bind the OAuth callback to loopback only ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Move runtime images to Alpine and retain dependency, secret, static-analysis, and container-image security scans ([b6bfb8b](https://github.com/MaximeMichaud/oura-dashboard/commit/b6bfb8b1eb8a83f73232c6d45dcb70c47c54cf56))
* Avoid storing the account email returned by `personal_info`.

### Bug Fixes

* Use Oura's current Cloud authorization endpoint and API token endpoint, resolving OAuth failures for newly registered applications ([#46](https://github.com/MaximeMichaud/oura-dashboard/issues/46), [51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Preserve successful endpoint cursors when another endpoint fails, and expose per-endpoint failures without reporting a false healthy state ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Handle malformed token responses, expired legacy tokens, pagination cycles, bounded rate-limit retries, singleton API payloads, and timezone-aware datetime ranges ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Fix the Sleep contributors table when Matplotlib is not installed and make navigation favicons consistent across Streamlit pages ([3a1a81d](https://github.com/MaximeMichaud/oura-dashboard/commit/3a1a81d623998b1e33115316f5f914638f8e342d))
* Use the PostgreSQL 18-compatible data directory layout ([6bdea99](https://github.com/MaximeMichaud/oura-dashboard/commit/6bdea99aaebe8a39d9b2d62ea179a5279c0b4861))

### Reliability and Performance

* Separate short lookback windows for day-based and high-volume time-series endpoints, reducing unnecessary heart-rate downloads while preserving late-arriving records ([51b946e](https://github.com/MaximeMichaud/oura-dashboard/commit/51b946e44dd6057df32deed08a7b852e15d286ae))
* Make endpoint upserts, retries, and synchronization accounting deterministic and independently testable ([cad75b0](https://github.com/MaximeMichaud/oura-dashboard/commit/cad75b0c7c285d1a8eb143572a2fd2061661e031))
* Remove the unused Matplotlib runtime dependency after replacing Pandas gradient styling with native formatting ([d46b6f2](https://github.com/MaximeMichaud/oura-dashboard/commit/d46b6f279bb2c929e2456e9699b3999fe12a3a2c))

### Quality Assurance

* Run integration tests against the actual Docker Compose topology, automatically migrated schema, read-only Grafana datasource, and Streamlit health endpoint ([3cb166c](https://github.com/MaximeMichaud/oura-dashboard/commit/3cb166cdd8af4f834b6979a51c8f6f5f916f8579))
* Seed representative data and exercise every Streamlit page and every Grafana panel in headless browser tests ([862bd45](https://github.com/MaximeMichaud/oura-dashboard/commit/862bd452f1cffeec0464f9307865b1c91a3233dd))
* Enforce 93% branch-aware coverage. The current suite contains 251 tests and reports 99.77% statement coverage and 99.26% branch-aware coverage ([9d3163d](https://github.com/MaximeMichaud/oura-dashboard/commit/9d3163d609ba2af3b9037ef536d1471a06ab2605))
* Complete a live OAuth authorization, callback, token exchange, persistence, refresh, and API-access smoke test against a newly registered Oura application.

### Dependencies and Tooling

* Upgrade PostgreSQL from 16 to 18 and Grafana from 12.3.3 to 13.1.0 ([738de8b](https://github.com/MaximeMichaud/oura-dashboard/commit/738de8bdc234de002aaa44999ade29ea7c0f39e2), [5091dea](https://github.com/MaximeMichaud/oura-dashboard/commit/5091dead4a8f1a1b76e4e9f92197e1d9e459c526))
* Consolidate dependency updates under Renovate and remove redundant auto-merge approval logic so required checks remain the merge gate ([90ef2c3](https://github.com/MaximeMichaud/oura-dashboard/commit/90ef2c3f926a6c086b4f289d24eb9b824613c8d1), [137794c](https://github.com/MaximeMichaud/oura-dashboard/commit/137794cb47a6d07c8749117db7b50f1ec4e2d6ac))

### Compatibility

* Existing personal access tokens remain supported through `OURA_TOKEN`.
* OAuth and legacy-token configurations can coexist; OAuth takes over when a valid OAuth token is available.
* Fresh installations are initialized automatically by the migration service.
* `ring_configuration` support includes current Oura Ring 4 data when the Oura API returns it. An empty response is valid for accounts or devices where Oura exposes no configuration record.

### Known Limitations

* OAuth still requires an Oura developer application and one interactive browser approval per account.
* Grafana requires synchronized Oura data; only the Streamlit interface provides demo data when credentials are unavailable.
* Oura app-only features such as Live Activity Tracking, Lab Uploads, Locate, and Metabolic Health are not available through the public Oura API v2 and are therefore not included in this release.

### Acknowledgements

Thanks to [@volcs0](https://github.com/volcs0) for reporting the OAuth endpoint incompatibility in [#46](https://github.com/MaximeMichaud/oura-dashboard/issues/46).

**Full Changelog:** https://github.com/MaximeMichaud/oura-dashboard/compare/v0.2.0...v0.3.0

## [0.2.0](https://github.com/MaximeMichaud/oura-dashboard/compare/v0.1.0...v0.2.0) (2026-03-27)


### Features

* add CLI flags, chunked streaming, and sync overlap guard ([2ec27d9](https://github.com/MaximeMichaud/oura-dashboard/commit/2ec27d9318d5a663466ce49beb7ae1d4b27e0067))
* add schema hardening, sync_history, and security improvements ([c6fba72](https://github.com/MaximeMichaud/oura-dashboard/commit/c6fba7293ae3c690c3f03bbad3e7d69d36bc8df8))
* add sleep_primary materialized view and improve wait_for_db logging ([4ec1c8b](https://github.com/MaximeMichaud/oura-dashboard/commit/4ec1c8bbc05d136f203534862d00c445169c9dac))
* add Streamlit dashboard frontend ([1c941b9](https://github.com/MaximeMichaud/oura-dashboard/commit/1c941b94073d972077964ea0d7af24409b690255))
* add sync status, weekly trends, activity targets, alerting, and integration tests ([b704d71](https://github.com/MaximeMichaud/oura-dashboard/commit/b704d7109f19ddc3cf22a6b98415d4e9a28f8866))
* Docker hardening, healthchecks, and cleanup ([b7d7063](https://github.com/MaximeMichaud/oura-dashboard/commit/b7d706386769cacf1b88d83b2659767278559104))
* fix stat panels time range, add VO2 Max panels, fix unit labels ([420b8a4](https://github.com/MaximeMichaud/oura-dashboard/commit/420b8a4e95dbfeca82f3c1e60835d5690638dade))


### Bug Fixes

* address 12 issues found during full codebase audit ([3c59142](https://github.com/MaximeMichaud/oura-dashboard/commit/3c5914212cf13f62c4569c14cc9b5615b41d5cd6))
* **ci:** remove polling loop from auto-merge workflow ([8f79008](https://github.com/MaximeMichaud/oura-dashboard/commit/8f790083def8771932130743f46aa8df9ce20fe9))
* **ci:** resolve auto-merge, security and dependabot failures ([82e7a82](https://github.com/MaximeMichaud/oura-dashboard/commit/82e7a826260c8574df3f3d378f09f77663a70cc4))
* **ci:** trigger CI on release-please PR branch ([1f415b8](https://github.com/MaximeMichaud/oura-dashboard/commit/1f415b8db19cbe8e820722f8eae66ba0c436aa3c))
* correct table count and document all env vars in README ([6bb3d8d](https://github.com/MaximeMichaud/oura-dashboard/commit/6bb3d8d03ae0c0770b44ba9e11a28d41d5aeb46e))
* **deps:** update tenacity requirement from &lt;9,&gt;=8.2 to &gt;=8.2,&lt;10 in /ingestion ([#2](https://github.com/MaximeMichaud/oura-dashboard/issues/2)) ([0634bd5](https://github.com/MaximeMichaud/oura-dashboard/commit/0634bd5ddb9a9f7e353fe0fd122cc0ca2489768a))
* fix Grafana datasource auth and VO2 Max API path ([8ab6c95](https://github.com/MaximeMichaud/oura-dashboard/commit/8ab6c955f0e00ed85f330fd35cc5b755a5a702d9))
* handle NULL last_sync_date in _get_start_date to prevent resync blockage ([6d3f9b6](https://github.com/MaximeMichaud/oura-dashboard/commit/6d3f9b67f2ee721dd00c6ab0e8375af810b69e70))
* harden API client retry logic and sync error handling ([1088980](https://github.com/MaximeMichaud/oura-dashboard/commit/1088980ee8150e27ccff6780d90d07c7df9bd92a))
* persist sidebar timezone and time range across pages and refreshes ([d1e6624](https://github.com/MaximeMichaud/oura-dashboard/commit/d1e662429fcfde4e1f5a7591092512dae596b650))


### Performance Improvements

* consolidate duplicate Grafana queries across 3 dashboards ([ae5938c](https://github.com/MaximeMichaud/oura-dashboard/commit/ae5938cf494e03a1259728305062fdebe69f29b2))
