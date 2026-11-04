# Changelog

## 1.3.0 — Salon operations and release candidate
- Added staff accounts with admin, manager, receptionist, cashier and barber roles, route-level authorization, and barber appointment scoping.
- Added weekly barber shifts, time-off periods, actual customer availability slots, and schedule-change conflict checks.
- Separated appointment completion from payment collection; disallowed invalid future completion and terminal-state reopening.
- Added payment method bookkeeping and one-time appointment refund entries.
- Added customer booking lookup using booking ID and matching phone without returning customer phone data.
- Added SQLite migration from the 1.2.2 schema without dropping existing salon records.
- Added admin-only consistent database backup and last-active-admin protection.
- Hardened monetary rounding, date validation, concurrent appointment updates, and customer-facing timezone handling.
- Expanded API/business-rule tests and added Windows/Android release build validation.
- Refunding an upcoming booking now cancels it and releases the barber slot; refunds after completed services remain financial adjustments.
- Customer availability lookups ignore stale concurrent responses when a service/date/barber selection changes quickly.
- Explicitly documented that payment methods are accounting records, not a payment gateway.

## 1.2.2 — branded desktop release candidate
- Added a multi-resolution Windows ICO generated from the official SALOON DREEM logo.
- Embedded the icon into the portable EXE metadata and Electron window/taskbar.
- Updated the optional Windows desktop shortcut to use the application's icon.
- Updated package, API, UI footer and offline-shell cache version to 1.2.2.
- Rebuilt Windows portable EXE and Android Debug APK through GitHub Actions.

## 1.2.1 — Recovery candidate
- Reassembled runnable source from individually CRC-verified files.
- Added release validation and portable Windows / Android debug build workflows.
- Applied CSV formula neutralization to exported appointment fields.
- Added SQLite immediate locking around appointment creation and payment recording.
- Documented Android's HTTPS API requirement and external payment limitations.
- The original TypeScript source and original ZIP were not fully recovered; the checked-in browser JavaScript bundle is used.
