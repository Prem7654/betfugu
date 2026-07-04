#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, field, value from HAR report.

Flow (all HAR-verified):
  0. Follow short refer link → 302 redirect → extract partner code
     (HAR Entry 3: s.betfugu01.com/ezzwvl51eipuy39 → 302)
     (HAR Entry 8: betfugu02.com/app/index.html?userId=2335316&partner=66666666)
  1. Generate random Indian phone (starts 6/7/8/9, 10 digits)
  2. Register      : POST /user/register/account  (partner from redirect, itemuserfor=freespin)
  3. Login        : POST /user/login/account     (returns token)
  4. Gift status  : GET  /opendata/homepage/registGifts  (check claimed=false)
  5. Homepage    : POST /opendata/homepage/indexV4  (load config)
  6. Free package: POST /user/profile/getfreepackage  (check package)
  7. Claim gift   : POST /user/profile/claimRegistGifts  (freespinbet10 x10)
  8. Free package2: POST /user/profile/getfreepackage  (verify after claim)
  9. Subscribe    : POST /freetinygames/freespin/subscribe  (tyid=freespinbet10)
 10. Play 10x    : POST /freetinygames/freespin/bet  (10 calls, until tycount=0)

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
PATH_REGIST_GIFTS = "/opendata/homepage/registGifts"
PATH_INDEX_V4 = "/opendata/homepage/indexV4"
PATH_GET_FREEPACKAGE = "/user/profile/getfreepackage"
PATH_CLAIM_GIFT = "/user/profile/claimRegistGifts"
PATH_SET_LANGUAGE = "/user/profile/setlanguage"
PATH_FREESPIN_SUBSCRIBE = "/freetinygames/freespin/subscribe"
PATH_FREESPIN_BET = "/freetinygames/freespin/bet"

# HAR Entry 271: itemuserfor = "freespin"
VERIFIED_ITEMUSERFOR = "freespin"
# HAR Entry 288: gift id and count
EXPECTED_GIFT_ID = "freespinbet10"
EXPECTED_GIFT_NUM = 10
# HAR Entry 618: subscribe request body
SUBSCRIBE_TYID = "freespinbet10"
# HAR Entries 624-651: 10 bet calls, final tycount=0
NUM_SPINS = 10
FIXED_PASSWORD = "123456"
# HAR Entry 298: setlanguage request body
SET_LANGUAGE = "en-US"

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

REDIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def call_api(method, host, path, body=None, token=None, extra_params=None):
    """Make single API call, return (http_status, response_json).

    Key: if body is None, urllib sends NO request body at all.
    If body is {}, urllib sends b'{}' which some BetFugu endpoints reject with 404.
    HAR proves: getfreepackage, claimRegistGifts, indexV4, freespin/bet
    have NO request body section → must use body=None.
    """
    url = host + path
    if extra_params:
        url += "?" + urlencode(extra_params)

    # Only send data if body is explicitly not None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None

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


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent urllib from auto-following 302 redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def follow_short_link_and_get_partner(short_url):
    """
    Follow short refer link → 302 redirect → extract partner code and userId.
    HAR proof:
      Entry 3:  GET s.betfugu01.com/ezzwvl51eipuy39 → 302 (text/html, 123 bytes)
      Entry 8:  GET betfugu02.com/app/index.html?userId=2335316&cury=INR&partner=66666666&rtm=...
    """
    req = urllib.request.Request(short_url, headers=REDIRECT_HEADERS, method="GET")
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        resp = opener.open(req, timeout=15)
        final_url = resp.url
    except urllib.error.HTTPError as e:
        if e.code == 302:
            final_url = e.headers.get("Location", "")
        else:
            raise

    if not final_url:
        return None, None, "No redirect Location found"

    parsed = urlparse(final_url)
    params = parse_qs(parsed.query)
    partner = params.get("partner", [None])[0]
    user_id = params.get("userId", [None])[0]

    if not partner or partner == "undefined":
        return None, None, "Partner not found in redirect URL: {}".format(final_url)

    return partner, user_id, final_url


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


def step_check_regist_gifts(token):
    """HAR Entry 280 — GET /opendata/homepage/registGifts
    Response: {"code":200,"data":{"claimed":false,"config":{"items":[{"id":"freespinbet10","num":10}]}}}
    Must be called BEFORE claimRegistGifts — server expects this check first.
    """
    status, resp = call_api("GET", H5_HOST, PATH_REGIST_GIFTS, token=token)
    if status != 200:
        return False, "Gift status FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Gift status FAIL: {}".format(resp)
    data = resp.get("data", {})
    claimed = data.get("claimed")
    return True, "Gift status OK (claimed={})".format(claimed)


def step_homepage_index_v4(token):
    """HAR Entry 286 — POST /opendata/homepage/indexV4
    Loads homepage config. HAR shows NO request body → use body=None.
    Must be called before claim — server expects this sequence.
    """
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body=None, token=token)
    if status != 200:
        return False, "Homepage FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Homepage FAIL: {}".format(resp)
    return True, "Homepage config OK ✅"


def step_get_free_package(token):
    """HAR Entry 283 — POST /user/profile/getfreepackage  (before claim)
    Response before claim: {"code":200,"freePackage":{},"confs":{}}
    HAR shows NO request body section → must use body=None (not {}).
    Sending body={} causes 404 Not Found.
    """
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body=None, token=token)
    if status != 200:
        return False, "Free package FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Free package FAIL: {}".format(resp)
    return True, "Free package OK ✅ (before claim)"


def step_claim_gift(token):
    """HAR Entry 288 — POST /user/profile/claimRegistGifts
    Response: {"code":200,"items":[{"id":"freespinbet10","num":10}]}
    HAR shows NO request body section → must use body=None (not {}).
    """
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body=None, token=token)
    if status != 200:
        return False, "Claim gift FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Claim gift FAIL: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM
               for i in items)
    if not found:
        return False, "Gift mismatch: {}".format(items)
    return True, "Gift claimed ✅ freespinbet10 x10"


def step_get_free_package_after_claim(token):
    """HAR Entry 293 — POST /user/profile/getfreepackage  (after claim)
    Response after claim: {"code":200,"freePackage":{"freespinbet10":10},"confs":{...}}
    HAR shows NO request body → use body=None.
    """
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body=None, token=token)
    if status != 200:
        return False, "Free package (after) FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Free package (after) FAIL: {}".format(resp)
    free_pkg = resp.get("freePackage", {})
    if EXPECTED_GIFT_ID in free_pkg:
        return True, "Free package verified ✅ freespinbet10={}x".format(free_pkg[EXPECTED_GIFT_ID])
    return True, "Free package after claim: {}".format(free_pkg)


def step_set_language(token):
    """HAR Entry 298 — POST /user/profile/setlanguage
    Body: {"language":"en-US"}
    HAR shows explicit request body → use body={"language":"en-US"}
    """
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token)
    if status != 200:
        return False, "Set language FAIL: HTTP {}".format(status)
    if resp.get("code") != 200:
        return False, "Set language FAIL: {}".format(resp)
    return True, "Language set ✅ (en-US)"


def step_freespin_subscribe(token):
    """HAR Entry 618 — POST /freetinygames/freespin/subscribe
    Body: {"tyid":"freespinbet10"}
    HAR shows explicit request body → use body={"tyid":"freespinbet10"}
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
    HAR shows NO request body → use body=None.
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


def run_full_flow(refer_link):
    """Run complete auto-registration + free spin flow."""
    report = []

    # Step 0 — Follow short link, extract partner
    report.append("🎰 BetFugu Auto-Register")
    report.append("Refer link: {}".format(refer_link))
    partner, user_id, redirect_url = follow_short_link_and_get_partner(refer_link)
    if not partner:
        report.append("❌ Partner extract FAIL: {}".format(redirect_url))
        return False, "\n".join(report)
    report.append("Partner: {} (from 302 redirect)".format(partner))
    if user_id:
        report.append("Referrer userId: {}".format(user_id))
    report.append("")

    phone = generate_random_phone()
    password = FIXED_PASSWORD

    report.append("Phone: {}".format(phone))
    report.append("Password: {}".format(password))
    report.append("")

    # Step 1 — Register
    ok, msg = step_register(phone, password, partner)
    report.append("1️⃣ Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 2 — Login
    token, msg = step_login(phone, password)
    report.append("2️⃣ Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    # Step 3 — Check gift status (HAR Entry 280)
    ok, msg = step_check_regist_gifts(token)
    report.append("3️⃣ Gift status: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 4 — Homepage config (HAR Entry 286)
    ok, msg = step_homepage_index_v4(token)
    report.append("4️⃣ Homepage: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 5 — Free package check (HAR Entry 283 — before claim)
    ok, msg = step_get_free_package(token)
    report.append("5️⃣ Free package (pre): {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 6 — Claim gift (HAR Entry 288)
    ok, msg = step_claim_gift(token)
    report.append("6️⃣ Claim gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 7 — Free package check (HAR Entry 293 — after claim)
    ok, msg = step_get_free_package_after_claim(token)
    report.append("7️⃣ Free package (post): {}".format(msg))

    # Step 8 — Set language (HAR Entry 298)
    ok, msg = step_set_language(token)
    report.append("8️⃣ Language: {}".format(msg))

    # Step 9 — Subscribe to free spin (HAR Entry 618)
    ok, msg = step_freespin_subscribe(token)
    report.append("9️⃣ Subscribe: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 10 — Play 10 free spins (HAR Entries 624-651)
    report.append("🔟 Playing 10 free spins...")
    ok, spin_report = step_play_spins(token)
    report.append(spin_report)
    report.append("")
    report.append("✅ Done! Registration + 10 free spins complete.")

    return True, "\n".join(report)


# ---- Telegram Bot Commands ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎰 *BetFugu Auto-Register Bot*\n\n"
        "HAR-verified — no guessing.\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` — refer link do, bot auto register + 10 free spins kheliga\n"
        "`/help` — help\n\n"
        "Example:\n"
        "`/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /register <REFER_LINK>
    Refer link format: https://s.betfugu01.com/xxxxx
    Bot follows 302 redirect → extracts partner → registers → plays spins.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Refer link do!\n\n"
            "Use: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
            parse_mode="Markdown",
        )
        return

    refer_link = " ".join(context.args)

    msg = await update.message.reply_text(
        "🔄 Processing refer link...\n{}".format(refer_link)
    )

    success, report = run_full_flow(refer_link)

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
        "• Short refer link follow → 302 redirect → partner code extract\n"
        "• Random 10-digit phone (6/7/8/9 se start)\n"
        "• Password: 123456\n"
        "• Register → Login → Gift check → Homepage → Free pkg → Claim → Play 10 spins\n\n"
        "Example:\n"
        "`/register https://s.betfugu01.com/ezzwvl51eipuy39`\n\n"
        "Verified from HAR (10 steps):\n"
        "0. Short link → 302 → partner (Entry 3→8)\n"
        "1. Register: POST /user/register/account (Entry 271)\n"
        "2. Login: POST /user/login/account (Entry 274)\n"
        "3. Gift check: GET /opendata/homepage/registGifts (Entry 280)\n"
        "4. Homepage: POST /opendata/homepage/indexV4 (Entry 286)\n"
        "5. Free pkg: POST /user/profile/getfreepackage (Entry 283)\n"
        "6. Claim: POST /user/profile/claimRegistGifts (Entry 288)\n"
        "7. Free pkg: POST /user/profile/getfreepackage (Entry 293)\n"
        "8. Language: POST /user/profile/setlanguage (Entry 298)\n"
        "9. Subscribe: POST /freetinygames/freespin/subscribe (Entry 618)\n"
        "10. Bet x10: POST /freetinygames/freespin/bet (Entries 624-651)",
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
