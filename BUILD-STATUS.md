# Build status — SALOON DREEM 1.3.0

This branch contains the 1.3.0 release candidate. Local validation completed successfully: 12 API/business-rule tests passed; Python modules compile; JavaScript syntax checks pass; and required web assets validate.

The GitHub release workflow on `release/v1.3.0-production` must still build and verify the Windows x64 portable EXE and Android Debug APK on their native runners. Release assets are published only after both builds and source validation pass. Refunding a pending/confirmed appointment also cancels it to release the barber's slot; a refund after a completed service remains a ledger adjustment without rewriting service history.

The Windows bundle includes the pinned IANA `tzdata` package so the configured salon timezone is available on Windows as well as Linux. The 1.3.0 source migrates the 1.2.2 SQLite schema in place and tests preservation of existing users, appointments, customers, and ledger entries. Always back up a real database before upgrading and test restoration separately.

Known product boundaries: no external card/bank payment processor, SMS/OTP, WhatsApp or calendar integration; customer lookup is booking-ID-plus-phone rather than a fully authenticated customer account; Android needs a reachable HTTPS API; Windows requires a trusted Authenticode certificate to obtain a publisher signature; Android store release needs a production signing key.
