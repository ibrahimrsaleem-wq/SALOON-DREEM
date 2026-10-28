# SALOON DREEM — 1.1.0

Arabic-first salon and barber-shop management application.

## Full source package
The complete application source, tests, documentation, desktop/mobile configuration and build workflows are provided in **SALOON-DREEM-1.1.0-source.zip** in this repository. Download the ZIP and extract it to work with the source tree.

## Included
- FastAPI backend and SQLite data store
- Arabic right-to-left responsive client and salon management interface
- Appointment scheduling and conflict checks
- Barbers, services, customers and cash ledger
- PWA/mobile configuration and Electron/Windows packaging setup
- Tests, Docker configuration, CI/build workflow source and deployment documentation

## Quick start (Windows)
1. Download and extract the source ZIP.
2. Install Python 3.12 or 3.13.
3. Run `RUN-SALOON-DREEM.bat`.
4. Open the local URL printed by the launcher and create the initial admin account.

## Validation report
The supplied source package was checked with 7 API tests, TypeScript checking, JavaScript syntax checking and Python compile checks.

## Important deployment notes
This is an initial runnable release, not yet a fully operated production service. Cloud multi-device hosting, external payments, WhatsApp/SMS notifications and live Android API hosting need additional deployment and integration configuration. The Android app needs a reachable HTTPS API endpoint.

## Security
Do not commit a real `.env`, database, access token or production secret. Use `.env.example` as a template.
