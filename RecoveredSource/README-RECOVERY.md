# SALOON-DREEM source salvage report

Only files that could be read and matched their ZIP CRC were preserved. This is a partial forensic recovery, not a complete release package.

## main-1.1.0-drop-first-char
- CRC-verified files: 0
- Entries seen: 0
- SHA-256 of recovered ZIP: 8739c76e681f900923b900c9df0ef75cf421d39cabb54650c4b9ad19b6a76d85
- Rejected/corrupt entries: 0

## main-1.1.0-drop-last-char
- CRC-verified files: 30
- Entries seen: 32
- SHA-256 of recovered ZIP: a56c01573ef819bc32fd1db04b03839fe5cef43936b1e2c6edea5937d42d6896
- Rejected/corrupt entries: 2

  - `SALOON-DREEM/frontend/src/app.ts`: Bad CRC-32 for file 'SALOON-DREEM/frontend/src/app.ts'
  - `SALOON-DREEM/tests/test_api.py`: Error -3 while decompressing data: invalid distance too far back
## package-1.2.0
- CRC-verified files: 14
- Entries seen: 19
- SHA-256 of recovered ZIP: df33ee9cd396e570477022a716c2208c42cceb1355f6e7d50fb9de0ee80794a5
- Rejected/corrupt entries: 1

  - `SALOOON-DDEEM/backend/app/server_entry.p`: Overlapped entries: 'SALOOON-DDEEM/backend/app/server_entry.p' (possible zip bomb)
## verified-1.2.0
- CRC-verified files: 25
- Entries seen: 35
- SHA-256 of recovered ZIP: 43068e597aeb47f31547233e6f84e0d471e3dd0b6a22c33a88c6632d1be42f35
- Rejected/corrupt entries: 2

  - `SALOON-DREEM/backend/app/main.py`: Bad CRC-32 for file 'SALOON-DREEM/backend/app/main.py'
  - `SALOOON-DREEM/frontend/icons/icon-192.pn`: Error -3 while decompressing data: invalid block type
