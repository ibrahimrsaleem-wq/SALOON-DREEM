# Deployment guide

## Local server

Use `RUN-SALOON-DREEM.ps1`. The normal browser installation serves frontend and API from one origin, so no external CORS list is needed.

## Docker host

Build from the repository using `docker compose up --build`. Attach/retain the named `saloon_data` volume. For a managed container host, set:

- `HOST=0.0.0.0`
- `PORT` to the port supplied by the host
- `APP_TIMEZONE=Asia/Gaza` (or the salon's actual IANA timezone)
- `DATA_DIR` and `DATABASE_PATH` to a persistent disk path
- `CORS_ORIGINS=https://localhost,capacitor://localhost,https://your-approved-web-origin.example` if the client is hosted on a separate origin
- `TOKEN_SECRET` to a long random secret held in the host's secret manager

The same-origin web UI and API are served together by FastAPI. Put HTTPS in front of the service using the hosting provider's TLS termination or a reverse proxy. Do not expose the unauthenticated setup endpoint to a public production instance before the initial administrator is established; restrict first-run setup to a trusted network.

## Mobile build

GitHub Actions builds a Capacitor Android project from `capacitor.config.json`. Add Actions variable `MOBILE_API_BASE_URL` with the deployment's HTTPS origin. API CORS must permit the Android WebView origins `https://localhost` and `capacitor://localhost` (the default configuration does). Build output is an installable debug APK, not a Play Store release bundle. A release APK/AAB should use a dedicated keystore stored as GitHub Secrets; never commit keystores/passwords.

## Windows build

The workflow bundles FastAPI, SQLite support, the frontend, and Uvicorn into a PyInstaller server executable, then packages it in Electron's Windows portable target. The portable runtime writes the database and token secret under Electron's per-user application-data directory, outside the extracted executable's temporary path.

## Backup and recovery

Back up `data/saloon_dreem.db` (for a local install) while the server is stopped, or use SQLite's online backup API for live systems. Store copies encrypted and away from the machine hosting the app. Restore-test backups before using the app for real customers. Preserve `data/.token-secret` for an existing local installation; replacing it invalidates existing sessions but does not erase database records.
