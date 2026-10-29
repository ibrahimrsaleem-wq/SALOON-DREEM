# Source restoration audit

This branch preserves `main` and verifies the source bundle before packaging.

The authoritative transfer package is `SALOON-DREEM-1.1.0-source.zip`, reconstructed from the numbered Base64 segments under `.source-package/`. The archive must match SHA-256:

`bdbeda15e54539a0fa56e3686a7c91c6f507e95fb5d9929afe709d5540b4a308`

Do not extract or distribute the package if its checksum fails. The workflow `.github/workflows/source-audit.yml` reconstructs and verifies the archive and publishes a temporary source artifact for inspection.
