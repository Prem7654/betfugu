# BetFugu Auto-Register + Free Spin Telegram Bot

HAR-verified bot — Telegram se refer link do, bot auto register karega + 10 free spins kheliga.

## Commands

| Command | Kaam |
|---|---|
| `/register <REFER_LINK>` | Auto register + 10 free spins |
| `/start` | Welcome |
| `/help` | Help |

## Flow (HAR-verified, no guessing)

| Step | Endpoint | HAR Entry | What happens |
|---|---|---|---|
| 1 | `POST /user/register/account` | 271 | Random phone (6/7/8/9), pass=123456, partner from link, itemuserfor=freespin |
| 2 | `POST /user/login/account` | 274 | Login → get auth token |
| 3 | `POST /user/profile/claimRegistGifts` | 288 | Claim freespinbet10 x10 |
| 4 | `POST /freetinygames/freespin/subscribe` | 618 | Subscribe with tyid=freespinbet10 |
| 5 | `POST /freetinygames/freespin/bet` x10 | 624-651 | Play 10 spins, final tycount=0 |

## Refer link format

Link me `partner=XXXXXX` hona chahiye:
```
https://betfugu02.com/?partner=66666666
```

Bot partner code extract karega aur use karega.

## Env variables (Railway)

```
BOT_TOKEN=<telegram-bot-token>
```

## Run locally

```bash
export BOT_TOKEN=your_token
python3 bot.py
```