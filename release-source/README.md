# SALOON DREEM 1.3.0 — complete source archive

This repository contains the complete application source tree at its root. The matching tested source snapshot is also stored at `release-source/SALOON-DREEM-source.tar.gz`.

Extract on Windows with 7-Zip, or in PowerShell:
```powershell
tar -xzf .\release-source\SALOON-DREEM-source.tar.gz
```

The archive omits secrets, local databases, virtual environments, and build caches. Start from `.env.example` and follow `docs/DEPLOYMENT.md`.
