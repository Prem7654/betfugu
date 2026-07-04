# BetFugu Registration Bot

HAR-verified registration-only bot for BetFugu. No guessing — every endpoint, field, and value comes from the HAR report.

## What it does

1. **Domain redirect** — `GET /opendata/domainRedirect` (Entry 96)
2. **Registration** — `POST /user/register/account` with partner `66666666`, itemuserfor `freespin` (Entry 271)
3. **Login** — `POST /user/login/account` → returns auth token (Entry 274)
4. **Claim registration gift** — `POST /user/profile/claimRegistGifts` → `freespinbet10` x10 (Entry 288)

No deposit, no spins, no payment — registration + gift claim only.

## Run locally

```bash
python3 bot.py --phone 91xxxxxxxxxx --password YourPass123
```

## Deploy on Railway

1. Fork / connect this repo to Railway
2. Add Variables:
   - `PHONE` — your phone number
   - `PASSWORD` — your password
3. Railway will run the Procfile command automatically

## Verified facts (from HAR)

| Fact | Value | HAR Entry |
|---|---|---|
| Partner code | `66666666` | 271 |
| itemuserfor | `freespin` | 271 |
| Gift ID | `freespinbet10` | 288 |
| Gift count | `10` | 288 |
| Domain | `betfugu02.com` (IN / INR) | 96 |
