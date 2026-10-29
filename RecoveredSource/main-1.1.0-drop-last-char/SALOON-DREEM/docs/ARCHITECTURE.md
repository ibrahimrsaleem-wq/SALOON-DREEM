# Architecture

## Components

- **Frontend:** Arabic RTL HTML/CSS, TypeScript source at `frontend/src/app.ts`, browser build output at `frontend/app.js`, service worker and PWA manifest.
- **API:** FastAPI in `backend/app/main.py`; typed request models, bearer authentication, validation and API documentation.
- **Persistence:** SQLite database with foreign keys, indexes, settings, appointment history and a financial cashbook.
- **Desktop:** Electron shell in `desktop/main.cjs`; it starts the local API on a free loopback port and stores data under the current OS user's application-data directory.
- **Android:** Capacitor 8 project generated during GitHub Actions, wraps the browser assets into an APK. The API must be hosted separately over HTTPS for normal off-device use.
- **Delivery:** CI tests and checks source; a second workflow builds the Windows portable executable and Android debug APK.

## Main data model

- `users`: initial administrator account and password hash.
- `services`: name, description, duration, price and active status.
- `barbers`: team member profile, specialty, contact and active status.
- `customers`: customer name, contact data and notes.
- `appointments`: customer/service/barber relations, interval, lifecycle status, price snapshot and payment status.
- `transactions`: income/expense lines; collecting an appointment creates one linked income transaction, guarded by a unique partial index.
- `settings`: business name, hours, currency, theme and contact details.

## Appointment flow

1. The customer selects an active service and sends their name, phone, requested time and optional barber.
2. The API parses the requested local time, rejects past appointments, derives the end time from the service duration and validates opening hours.
3. The API picks an active barber (or uses the requested one), checks for interval overlap, and returns `409 Conflict` when the slot is already occupied.
4. The customer record is created or matched by phone. The appointment is stored as `pending` for staff review.
5. Staff confirms/cancels/completes the appointment. Collecting payment creates a linked income entry and marks the appointment paid/completed.

## Security design and remaining work

Passwords use PBKDF2-HMAC-SHA256 with per-password random salts. API access tokens are HMAC-signed and expire. The application generates a stable per-installation token secret if one is not configured. CORS is restricted to configured origins, with Capacitor localhost origins allowed by default.

Before public production deployment, add explicit staff roles and audit records, request rate limiting, tested automated backups/restore, verified customer identity for cross-device booking history, SMS/email delivery integration, production Android signing keys, Windows code signing, and a managed database when concurrency/scale requires it. Do not treat the local customer profile or loyalty view as an identity-verification mechanism.
