# BetFugu Registration Telegram Bot

HAR-verified registration bot for BetFugu — Telegram se chalta hai.
No guessing — every endpoint, field, value HAR report se verified.

## Commands

| Command | Kaam |
|---|---|
| `/start` | Welcome + help |
| `/register PHONE PASSWORD` | BetFugu pe account register + gift claim |
| `/help` | Full help

## Verified flow (HAR evidence)

| Step | Endpoint | HAR Entry | Result |
|---|---|---|---|
| 1 | `GET /opendata/domainRedirect?domain=betfugu02.com` | 96 | domain `betfugu02.com`, IN/INR |
| 2 | `POST /user/register/account` | 271 | partner `66666666`, itemuserfor `freespin` → code 200 |
| 3 | `POST /user/login/account` | 274 | returns auth token |
| 4 | `POST /user/profile/claimRegistGifts` | 288 | `freespinbet10` x10 |

## Env variables (Railway Variables tab)

```
BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
```

`BOT_TOKEN` — @BotFather se lo Telegram pe.

## Deploy on Railway

1. Railway pe repo connect karo
2. Variables → `BOT_TOKEN` add karo
3. Railway automatically `Procfile` se `python3 bot.py` run karega
4. Telegram pe apne bot ko `/register PHONE PASSWORD` bhejo

## Run locally

```bash
export BOT_TOKEN=your_telegram_token
python3 bot.py
```

## Requirements

- Python 3.11+
- `python-telegram-bot==21.6`
