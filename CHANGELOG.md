# Changelog

## [0.3.0](https://github.com/MaximeMichaud/oura-dashboard/compare/v0.2.0...v0.3.0) (2026-03-27)


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
* correct table count and document all env vars in README ([6bb3d8d](https://github.com/MaximeMichaud/oura-dashboard/commit/6bb3d8d03ae0c0770b44ba9e11a28d41d5aeb46e))
* **deps:** update tenacity requirement from &lt;9,&gt;=8.2 to &gt;=8.2,&lt;10 in /ingestion ([#2](https://github.com/MaximeMichaud/oura-dashboard/issues/2)) ([7e0efe0](https://github.com/MaximeMichaud/oura-dashboard/commit/7e0efe0cef700408ccfba3729cddf7ce636a6783))
* fix Grafana datasource auth and VO2 Max API path ([8ab6c95](https://github.com/MaximeMichaud/oura-dashboard/commit/8ab6c955f0e00ed85f330fd35cc5b755a5a702d9))
* handle NULL last_sync_date in _get_start_date to prevent resync blockage ([6d3f9b6](https://github.com/MaximeMichaud/oura-dashboard/commit/6d3f9b67f2ee721dd00c6ab0e8375af810b69e70))
* harden API client retry logic and sync error handling ([1088980](https://github.com/MaximeMichaud/oura-dashboard/commit/1088980ee8150e27ccff6780d90d07c7df9bd92a))
* persist sidebar timezone and time range across pages and refreshes ([d1e6624](https://github.com/MaximeMichaud/oura-dashboard/commit/d1e662429fcfde4e1f5a7591092512dae596b650))


### Performance Improvements

* consolidate duplicate Grafana queries across 3 dashboards ([ae5938c](https://github.com/MaximeMichaud/oura-dashboard/commit/ae5938cf494e03a1259728305062fdebe69f29b2))

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
