# Security policy

SALOON DREEM is an early release intended for validation and controlled deployment. Do not put production customer data in a publicly exposed instance until the deployment checklist in `docs/DEPLOYMENT.md` is completed.

## Reports

Please do not publish passwords, access tokens, personal customer data, database files, or screenshots containing private information in public issues. Report suspected security issues privately to the repository owner through GitHub's private vulnerability reporting if enabled.

## Operational safeguards

- Keep `.env`, token secrets, SQLite files, signing keys and signing passwords out of version control.
- Use HTTPS, strong unique administrator credentials and a private persistent database volume.
- Restrict initial setup and administrative access; take encrypted backups and test restoration.
- Use a trusted identity verification channel before showing a customer their appointment history across devices.
