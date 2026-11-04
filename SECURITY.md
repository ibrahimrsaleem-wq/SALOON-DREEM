# Security policy

SALOON DREEM contains customer contact details and financial records. Deploy it only behind HTTPS with restricted administrative access and a persistent, access-controlled data volume.

## Operational safeguards

- Keep `.env`, `TOKEN_SECRET`, SQLite databases, customer exports, backups, signing keys and signing passwords out of version control.
- Use unique passwords and separate staff accounts; never share the owner account with reception or cashiers.
- Keep a second active administrator for account recovery. The API prevents disabling or demoting the final active administrator.
- Use the admin-only database backup endpoint, store encrypted backups outside the application host, and test restoration regularly.
- Do not expose SQLite files or backup downloads publicly. Keep the service behind HTTPS and configure trusted origins when using a separately hosted API.
- The process-local rate limiter is suitable for a single instance only. For multiple replicas, use a shared rate limiter and PostgreSQL.
- Payment method labels are bookkeeping only; do not use them as proof that a payment processor completed a transaction.

## Reporting

Please do not publish passwords, access tokens, private customer data, database files, or screenshots containing personal information in public issues. Report suspected security issues privately to the repository owner through GitHub's private vulnerability reporting if enabled.
