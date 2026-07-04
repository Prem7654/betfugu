#!/usr/bin/env python3
"""
BetFugu Registration Bot — Telegram + HAR-verified.

Telegram bot jo BetFugu pe account register karta hai.
Sirf verified HAR endpoints — no guessing.

Commands:
  /start          — Bot welcome + help
  /register       — Register karna (phone + password maangta hai)
  /register PHONE PASSWORD — Direct register

Verified endpoints (HAR report):
  1. Domain redirect  : GET  /opendata/domainRedirect?domain=betfugu02.com
  2. Registration       : POST /user/register/account  (partner:66666666, itemuserfor:freespin)
  3. Login              : POST /user/login/account    (returns token)
  4. Claim gift        : POST /user/profile/claimRegistGifts  (freespinbet10 x10)

Env variables:
  BOT_TOKEN  — Telegram Bot Token (@BotFather se lo)
"""

import os
import json
import urllib.request
import urllib.error
from urllib.parse import urlencode

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ---- Verified constants (from HAR report) ----
BASE_HOST = "https://h5server.betfuguapi.com"
PATH_DOMAIN_REDIRECT = "/opendata/domainRedirect"
PATH_REGISTER = "/user/register/account"
PATH_LOGIN = "/user/login/account"
PATH_CLAIM_GIFT = "/user/profile/claimRegistGifts"

VERIFIED_PARTNER = 66666666       # Entry 271 request body
VERIFIED_ITEMUSERFOR = "freespin" # Entry 271 request body
EXPECTED_GIFT_ID = "freespinbet10" # Entry 288 response body
EXPECTED_GIFT_NUM = 10              # Entry 288 response body

COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://betfugu02.com",
    "Referer": "https://betfugu02.com/",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    ),
}


def call_api(method, host, path, body=None, token=None, extra_params=None):
    """Make a single API call, return (http_status, response_json)."""
    url = host + path
    if extra_params:
        url += "?" + urlencode(extra_params)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = dict(COMMON_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"_raw": raw}
            return status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"_raw": raw}
        return e.code, parsed


# ---- BetFugu API steps (all HAR-verified) ----

def step_domain_redirect():
    """HAR Entry 96 — GET /opendata/domainRedirect?domain=betfugu02.com"""
    status, body = call_api("GET", BASE_HOST, PATH_DOMAIN_REDIRECT,
                            extra_params={"domain": "betfugu02.com"})
    if status != 200 or body.get("code") != 200:
        return False, "Domain redirect fail: {}".format(body)
    data = body.get("data") or {}
    if data.get("domain") != "betfugu02.com":
        return False, "Unexpected domain"
    return True, "Domain OK → betfugu02.com (IN / INR)"


def step_register(phone, password):
    """HAR Entry 271 — POST /user/register/account"""
    body = {
        "account": phone,
        "password": password,
        "partner": VERIFIED_PARTNER,
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    status, resp = call_api("POST", BASE_HOST, PATH_REGISTER, body=body)
    if status != 200 or resp.get("code") != 200:
        return False, "Registration fail: {}".format(resp)
    return True, "Account registered ✅ (server code 200)"


def step_login(phone, password):
    """HAR Entry 274 — POST /user/login/account → returns token"""
    body = {"account": phone, "password": password}
    status, resp = call_api("POST", BASE_HOST, PATH_LOGIN, body=body)
    if status != 200 or resp.get("code") != 200:
        return None, "Login fail: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login did not return token"
    return token, "Login ✅ — token received"


def step_claim_gift(token):
    """HAR Entry 288 — POST /user/profile/claimRegistGifts → freespinbet10 x10"""
    status, resp = call_api("POST", BASE_HOST, PATH_CLAIM_GIFT, body={}, token=token)
    if status != 200 or resp.get("code") != 200:
        return False, "Claim gift fail: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM
               for i in items)
    if not found:
        return False, "Gift item mismatch: {}".format(items)
    return True, "Gift claimed ✅ freespinbet10 x10"


def run_full_registration(phone, password):
    """Run all 4 HAR-verified steps. Returns (success, report_text)."""
    report = []

    # Step 1 — Domain redirect
    ok, msg = step_domain_redirect()
    report.append("1️⃣ Domain: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 2 — Register
    ok, msg = step_register(phone, password)
    report.append("2️⃣ Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 3 — Login
    token, msg = step_login(phone, password)
    report.append("3️⃣ Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    # Step 4 — Claim gift
    ok, msg = step_claim_gift(token)
    report.append("4️⃣ Gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    report.append("\n✅ Registration complete! No deposit, no spins — only register + gift.")
    return True, "\n".join(report)


# ---- Telegram Bot Commands ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    await update.message.reply_text(
        "🎰 *BetFugu Registration Bot*\n\n"
        "HAR-verified — no guessing.\n\n"
        "Commands:\n"
        "`/register PHONE PASSWORD` — direct register\n"
        "`/register` — step by step\n\n"
        "Verified partner: `66666666`\n"
        "Gift: `freespinbet10` x10",
        parse_mode="Markdown",
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /register PHONE PASSWORD
    or
    /register  (then bot asks for phone + password)
    """
    text = "🔄 Starting BetFugu registration...\nAll steps HAR-verified.\n\n"
    msg = await update.message.reply_text(text)

    if len(context.args) >= 2:
        phone = context.args[0]
        password = context.args[1]
    elif len(context.args) == 1:
        await msg.edit_text(text + "⚠️ Password bhi do!\n\nUse: `/register PHONE PASSWORD`", parse_mode="Markdown")
        return
    else:
        await msg.edit_text(text + "⚠️ Use: `/register PHONE PASSWORD`", parse_mode="Markdown")
        return

    success, report = run_full_registration(phone, password)

    full_text = text + "\n" + report
    # Telegram message limit = 4096 chars
    for i in range(0, len(full_text), 4000):
        chunk = full_text[i:i + 4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help message"""
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "`/start` — welcome\n"
        "`/register PHONE PASSWORD` — register karo BetFugu pe\n"
        "`/help` — ye message\n\n"
        "Verified from HAR:\n"
        "• Domain: betfugu02.com (IN/INR)\n"
        "• Partner: 66666666\n"
        "• itemuserfor: freespin\n"
        "• Gift: freespinbet10 x10",
        parse_mode="Markdown",
    )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN env variable set nahi hai!")
        print("Railway Variables tab mein BOT_TOKEN=xxx add karo")
        raise SystemExit(1)

    print("BetFugu TG Bot starting...")
    print("Token: {}...{}".format(token[:8], token[-3:]))

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))

    # Polling mode — Railway pe worker dyno use kar agar web dyno port error aaye
    print("Bot polling... waiting for Telegram commands.")
    app.run_polling()


if __name__ == "__main__":
    main()
