# Deployment guide

## Recommended topology

For one salon, deploy one FastAPI instance with its SQLite database on a persistent volume. Put it behind a TLS-terminating reverse proxy/platform HTTPS endpoint. Configure `HOST=0.0.0.0`, `DATA_DIR`, `DATABASE_PATH`, `APP_TIMEZONE` (an IANA timezone such as `Asia/Gaza`) and a random `TOKEN_SECRET` of at least 32 characters.

Do not run multiple application processes against the same SQLite file. The in-memory rate limiter is per process. For multiple locations, high concurrency or horizontal scaling, migrate to PostgreSQL and a shared rate limiter before adding replicas.

## Docker

```bash
docker compose up --build -d
docker compose logs -f saloon-dreem
```

The `saloon_data` volume stores `saloon_dreem.db` and `.token-secret`. Back up the volume regularly and test recovery in a separate environment.

## HTTPS and Android

Serve the web app and API through the same HTTPS origin where possible. Set the Android app's API base URL to that HTTPS origin, or configure `MOBILE_API_BASE_URL` during the build. Do not use cleartext HTTP for a remote API or embed credentials/secrets in `frontend/runtime-config.js`.

## First run

Open the site and create the first administrator. Configure the business name, timezone, currency, opening hours, services, staff and each barber's weekly shifts/time-off periods. Create a second administrator for account recovery before disabling or losing access to the first account.

## Backups

Use the admin-only `/api/backup` route from Settings to download a transactionally consistent SQLite snapshot. Store backup files outside the application host, encrypt them at rest, restrict access, and periodically restore one into a test instance. A backup contains personal customer and financial data and must be handled as confidential.

## Release build

The 1.3.0 release workflow validates source/API tests, builds Windows x64 Portable EXE and Android Debug APK, verifies the artifacts, and publishes a GitHub Release only if all required jobs pass. Neither artifact is a store-signed production package by default.
