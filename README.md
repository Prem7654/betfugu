# BetFugu Auto-Register + Free Spin Telegram Bot

HAR-verified bot — Telegram se refer link do, bot auto register karega + 10 free spins kheliga.

## Commands

| Command | Kaam |
|---|---|
| `/register <REFER_LINK>` | Auto register + 10 free spins |
| `/start` | Welcome |
| `/help` | Help |

## Refer link format

Short link jaise:
```
https://s.betfugu01.com/ezzwvl51eipuy39
```

Bot is link ko follow karega → 302 redirect se `partner` code extract karega.

## Flow (HAR-verified, no guessing)

| Step | Endpoint | HAR Entry | What happens |
|---|---|---|---|
| 0 | Follow short link → 302 redirect | 3→8 | Extract partner code from redirect URL |
| 1 | `POST /user/register/account` | 271 | Random phone (6/7/8/9), pass=123456, partner from link |
| 2 | `POST /user/login/account` | 274 | Login → get auth token |
| 3 | `POST /user/profile/claimRegistGifts` | 288 | Claim freespinbet10 x10 |
| 4 | `POST /freetinygames/freespin/subscribe` | 618 | Subscribe with tyid=freespinbet10 |
| 5 | `POST /freetinygames/freespin/bet` x10 | 624-651 | Play 10 spins, final tycount=0 |

## Env variables (Railway)

```
BOT_TOKEN=<telegram-bot-token>
```

## Run locally

```bash
export BOT_TOKEN=your_token
python3 bot.py
```