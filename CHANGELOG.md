# Changelog

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
