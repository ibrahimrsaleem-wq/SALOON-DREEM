# Changelog

## 1.1.0 — 2026-10-28

- Added FastAPI API test coverage for setup/auth, public bookings, schedule conflicts, payment recording, financial summary, settings and Capacitor CORS.
- Replaced deprecated FastAPI startup event with a lifespan handler.
- Fixed overnight business-hours validation and blocked rescheduling appointments into the past.
- Added settings input validation for opening hours, currency and theme.
- Fixed quick theme toggle event dispatch.
- Added mobile API runtime configuration, PWA PNG icons and cache-version update.
- Added Electron portable Windows packaging, PyInstaller server entry point and Capacitor Android build workflow.
- Added Docker configuration, deployment/security documentation and safe GitHub publish helper.

## 1.0.0 — Initial working codebase

- Arabic RTL PWA frontend and FastAPI + SQLite backend for appointments, services, barbers, customers, settings and cashbook.
