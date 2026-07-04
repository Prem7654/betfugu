#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, field, value from HAR report.

Flow (all HAR-verified):
  1. Parse partner code from user's refer link
  2. Generate random Indian phone (starts 6/7/8/9, 10 digits)
  3. Register  : POST /user/register/account  (partner from link, itemuserfor=freespin)
  4. Login      : POST /user/login/account     (returns token)
  5. Claim gift : POST /user/profile/claimRegistGifts  (freespinbet10 x10)
  6. Subscribe  : POST /freetinygames/freespin/subscribe  (tyid=freespinbet10)
  7. Play 10x   : POST /freetinygames/freespin/bet  (10 calls, until tycount=0)

Env:
  BOT_TOKEN  — Telegram bot token from @BotFather
"""

import os
import re
import json
import random
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlparse, parse_qs

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ---- Verified constants (from HAR report) ----
H5_HOST = "https://h5server.betfuguapi.com"
GAME_HOST = "https://game.betfuguapi.com"

PATH_REGISTER = "/user/register/account"
PATH_LOGIN = "/user/login/account"
PATH_CLAIM_GIFT = "/user/profile/claimRegistGifts"
PATH_FREESPIN_SUBSCRIBE = "/freetinygames/freespin/subscribe"
PATH_FREESPIN_BET = "/freetinygames/freespin/bet"

# HAR Entry 271: itemuserfor = "freespin"
VERIFIED_ITEMUSERFOR = "freespin"
# HAR Entry 288: gift id and count
EXPECTED_GIFT_ID = "freespinbet10"
EXPECTED_GIFT_NUM = 10
# HAR Entry 618: subscribe request body
SUBSCRIBE_TYID = "freespinbet10"
# HAR Entry 624-651: 10 bet calls, final tycount=0
NUM_SPINS = 10
FIXED_PASSWORD = "123456"

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
    """Make single API call, return (http_status, response_json)."""
    url = host + path
    if extra_params:
        url += "?" + urlencode(extra_params)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = dict(COMMON_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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


def parse_partner_from_link(link):
    """
    Extract partner code from refer link.
    HAR proves partner comes as URL param: partner=66666666
    (HAR lines 15870, 15944, 16312 — URL: ?partner=66666666)
    """
    try:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        partner = params.get("partner", [None])[0]
        if partner:
            return partner
    except Exception:
        pass
    # Try regex fallback if URL format different
    match = re.search(r'partner=(\d+)', link)
    if match:
        return match.group(1)
    return None


def generate_random_phone():
    """
    Generate random 10-digit Indian phone starting with 6, 7, 8, or 9.
    HAR Entry 271 shows account field = phone number.
    """
    first_digit = random.choice(["6", "7", "8", "9"])
    rest = "".join(random.choice("0123456789") for _ in range(9))
    return first_digit + rest


# ---- BetFugu API steps (all HAR-verified) ----

def step_register(phone, password, partner):
    """HAR Entry 271 — POST /user/register/account
    Body: {account, password, partner, itemuserfor:"freespin"}
    Response: {"code":200}
    """
    body = {
        "account": phone,
        "password": password,
        "partner": int(partner),
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body)
    if status != 200 or resp.get("code") != 200:
        return False, "Registration FAIL: {}".format(resp)
    return True, "Registered ✅ (code 200)"


def step_login(phone, password):
    """HAR Entry 274 — POST /user/login/account
    Body: {account, password}
    Response: {"code":200, "token":"..."}
    """
    body = {"account": phone, "password": password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body)
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login ✅"


def step_claim_gift(token):
    """HAR Entry 288 — POST /user/profile/claimRegistGifts
    Response: {"code":200,"items":[{"id":"freespinbet10","num":10}]}
    """
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token)
    if status != 200 or resp.get("code") != 200:
        return False, "Claim gift FAIL: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM
               for i in items)
    if not found:
        return False, "Gift mismatch: {}".format(items)
    return True, "Gift claimed ✅ freespinbet10 x10"


def step_freespin_subscribe(token):
    """HAR Entry 618 — POST /freetinygames/freespin/subscribe
    Body: {"tyid":"freespinbet10"}
    """
    body = {"tyid": SUBSCRIBE_TYID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: {}".format(resp)
    return True, "Subscribed ✅ (freespinbet10)"


def step_play_spins(token):
    """HAR Entries 624-651 — POST /freetinygames/freespin/bet
    10 calls. Each response has tycount (remaining spins).
    HAR proves: starts at tycount=9 (after 1st bet), ends at tycount=0.
    No request body required (HAR shows no request body for bet calls).
    """
    results = []
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body=None, token=token)
        if status != 200:
            results.append("Spin {}: ❌ HTTP {}".format(i+1, status))
            break
        game_data = resp.get("lotteryGameResult", {}).get("data", {})
        balance = game_data.get("balance", "?")
        win = game_data.get("win", 0)
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        results.append("Spin {}/{}: bet=10 win={} bal={} left={}".format(
            i+1, NUM_SPINS, win, balance, tycount))
        if tycount == 0 and i < NUM_SPINS - 1:
            break
    return True, "\n".join(results) + "\nTotal win: {}".format(total_win)


def run_full_flow(partner_code):
    """Run complete auto-registration + free spin flow."""
    report = []
    phone = generate_random_phone()
    password = FIXED_PASSWORD

    report.append("🎰 BetFugu Auto-Register")
    report.append("Phone: {}".format(phone))
    report.append("Password: {}".format(password))
    report.append("Partner: {} (from refer link)".format(partner_code))
    report.append("")

    # Step 1 — Register
    ok, msg = step_register(phone, password, partner_code)
    report.append("1️⃣ Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 2 — Login
    token, msg = step_login(phone, password)
    report.append("2️⃣ Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    # Step 3 — Claim gift
    ok, msg = step_claim_gift(token)
    report.append("3️⃣ Gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 4 — Subscribe to free spin
    ok, msg = step_freespin_subscribe(token)
    report.append("4️⃣ Subscribe: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 5 — Play 10 free spins
    report.append("5️⃣ Playing 10 free spins...")
    ok, spin_report = step_play_spins(token)
    report.append(spin_report)
    report.append("")
    report.append("✅ Done! Registration + 10 free spins khel diye.")

    return True, "\n".join(report)


# ---- Telegram Bot Commands ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎰 *BetFugu Auto-Register Bot*\n\n"
        "HAR-verified — no guessing.\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` — refer link do, bot auto register + 10 free spins kheliga\n"
        "`/help` — help\n\n"
        "Flow:\n"
        "1. Random phone (6/7/8/9 se start)\n"
        "2. Password: 123456\n"
        "3. Register → Login → Claim gift → Play 10 spins",
        parse_mode="Markdown",
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /register <REFER_LINK>
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Refer link do!\n\nUse: `/register https://betfugu02.com/...?partner=XXXXXX`",
            parse_mode="Markdown",
        )
        return

    refer_link = " ".join(context.args)
    partner = parse_partner_from_link(refer_link)

    if not partner:
        await update.message.reply_text(
            "❌ Refer link me partner code nahi mila.\n"
            "Link me `partner=XXXXXX` hona chahiye.\n\n"
            "Example: `/register https://betfugu02.com/?partner=66666666`",
            parse_mode="Markdown",
        )
        return

    msg = await update.message.reply_text(
        "🔄 Starting auto-registration...\n"
        "Partner: {}\n"
        "Generating random phone...".format(partner)
    )

    success, report = run_full_flow(partner)

    # Send report in chunks (Telegram 4096 char limit)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "`/register <REFER_LINK>` — auto register + 10 free spins\n\n"
        "Bot kya karta hai:\n"
        "• Refer link se partner code nikalta hai\n"
        "• Random 10-digit phone (6/7/8/9 se start)\n"
        "• Password: 123456\n"
        "• Register → Login → Claim gift → Subscribe → 10 spins khelta hai\n\n"
        "Verified from HAR:\n"
        "• Register: POST /user/register/account\n"
        "• Login: POST /user/login/account\n"
        "• Gift: POST /user/profile/claimRegistGifts\n"
        "• Subscribe: POST /freetinygames/freespin/subscribe\n"
        "• Bet: POST /freetinygames/freespin/bet (10x)",
        parse_mode="Markdown",
    )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN env variable set nahi hai!")
        print("Railway Variables me BOT_TOKEN=xxx add karo")
        raise SystemExit(1)

    print("BetFugu Auto-Register TG Bot starting...")
    print("Token: {}...{}".format(token[:8], token[-3:]))

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))

    print("Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
