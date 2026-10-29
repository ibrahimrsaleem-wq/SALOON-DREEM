# Changelog

## 1.2.0 — 2026-10-28

- Bind sessions to the current password hash so changing a password revokes previous access tokens.
- Add per-IP, process-local rate limits for initial setup, login attempts, and public appointment submissions.
- Serialize initial administrator setup to prevent concurrent first-run setup races.
- Re-check schedule conflicts when an appointment is moved or reactivated from cancelled status.
- Neutralize spreadsheet formula prefixes in appointment CSV exports.
- Validate date filters and date ranges before querying financial summaries and appointments.
- Add baseline security response headers and disable caching of API responses.
- Expand API tests from 7 to 12 test cases.

## 1.1.0 — API and desktop/mobile foundations

- Arabic RTL web app with FastAPI and SQLite.
- Appointment, customer, staff, service, settings, and cashbook APIs.
- PWA install metadata and Electron/Capacitor build configuration.
