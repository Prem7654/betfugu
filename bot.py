#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, header, body from original HAR file.

KEY FIX: Server uses `access-token` custom header (NOT `Authorization: Bearer`).
All 20+ custom headers from HAR are now included.
Body is always `{}` for POST calls (HAR proves bodySize=2, text='{}').

Flow (all HAR-verified):
  0. Follow short refer link -> 302 redirect -> extract partner code
  1. Generate random Indian phone (starts 6/7/8/9, 10 digits)
  2. Register    : POST /user/register/account  (partner, itemuserfor=freespin)
  3. Login      : POST /user/login/account    (returns token)
  4. Gift status : GET  /opendata/homepage/registGifts  (check claimed=false)
  5. Homepage   : POST /opendata/homepage/indexV4  (load config)
  6. Free package: POST /user/profile/getfreepackage  (check package)
  7. Claim gift  : POST /user/profile/claimRegistGifts  (freespinbet10 x10)
  8. Free pkg2  : POST /user/profile/getfreepackage  (verify after claim)
  9. Language   : POST /user/profile/setlanguage  (en-US)
 10. Subscribe   : POST /freetinygames/freespin/subscribe  (tyid=freespinbet10)
 11. Play 10x   : POST /freetinygames/freespin/bet  (10 calls, until tycount=0)

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

# ---- Verified constants (from original HAR file) ----
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

VERIFIED_ITEMUSERFOR = "freespin"
EXPECTED_GIFT_ID = "freespinbet10"
EXPECTED_GIFT_NUM = 10
SUBSCRIBE_TYID = "freespinbet10"
NUM_SPINS = 10
FIXED_PASSWORD = "123456"
SET_LANGUAGE = "en-US"

# ---- HAR-verified headers for H5 host (h5server.betfuguapi.com) ----
# These are the EXACT custom headers the browser sends (HAR Entry 283/286/288 etc.)
# Server REJECTS requests missing these headers (404 Not Found).
H5_BASE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://betfugu02.com",
    "referer": "https://betfugu02.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
    ),
    "language": "en-US",
    "appid": "wecardgame",
    "channel": "test",
    "currency": "INR",
    "version": "2.11.56",
    "timezone": "Asia/Calcutta",
    "tmoffset": "-330",
    "network": "4g",
    "publisher": "release",
    "platform": "Unknown",
    "basepkgname": "h5",
    "pkgname": "h5",
    "osv": "10",
    "weblang": "en-US",
    "weblangs": "en-US,en,en-IN",
    "isfrom": "other_pwa",
    "ispwa": "true",
    "webfonts": "Microsoft YaHei",
    "deviceid": "",
    "visitorid": "(null)",
    "sourceurl": "https://betfugu02.com/bf_pwa/index.html#/",
}

# ---- HAR-verified headers for GAME host (game.betfuguapi.com) ----
# Game host uses DIFFERENT headers (HAR Entry 618/624 etc.)
# Note: origin/referer use www.betfugu02.com (with www prefix)
GAME_BASE_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://www.betfugu02.com",
    "referer": "https://www.betfugu02.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
    ),
}

# Redirect link headers (for following short URL -> 302)
REDIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def call_api(method, host, path, body=None, token=None, partner=None, game=False):
    """Make single API call, return (http_status, response_json).

    HAR PROOF: All POST calls use body='{}' (bodySize=2). NOT None/empty.
    HAR PROOF: Token goes in `access-token` header (NOT `Authorization: Bearer`).
    HAR PROOF: H5 host needs ~25 custom headers. Game host needs ~6 basic headers.
    """
    url = host + path

    # HAR shows: POST calls send body='{}', GET calls send no body
    if method == "POST":
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        else:
            # HAR proves: empty POST calls use body='{}' (bodySize=2)
            data = b"{}"
    else:
        data = None

    # Pick correct header set based on host
    if game or host == GAME_HOST:
        headers = dict(GAME_BASE_HEADERS)
        if token:
            headers["access-token"] = token
    else:
        headers = dict(H5_BASE_HEADERS)
        if partner:
            headers["partner"] = str(partner)
        if token:
            # KEY FIX: server uses 'access-token' header, NOT 'Authorization: Bearer'
            headers["access-token"] = token

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
    Follow short refer link -> 302 redirect -> extract partner code and userId.
    HAR Entry 3:  GET s.betfugu01.com/ezzwvl51eipuy39 -> 302
    HAR Entry 8:  GET betfugu02.com/app/index.html?userId=2335316&cury=INR&partner=66666666
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
    """Generate random 10-digit Indian phone starting with 6, 7, 8, or 9."""
    first_digit = random.choice(["6", "7", "8", "9"])
    rest = "".join(random.choice("0123456789") for _ in range(9))
    return first_digit + rest


# ---- BetFugu API steps (all HAR-verified) ----

def step_register(phone, password, partner):
    """HAR Entry 271 - POST /user/register/account
    Body: {account, password, partner, itemuserfor:"freespin"}
    Response: {"code":200}
    """
    body = {
        "account": phone,
        "password": password,
        "partner": int(partner),
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body, partner=partner)
    if status != 200 or resp.get("code") != 200:
        return False, "Registration FAIL: {}".format(resp)
    return True, "Registered \u2705 (code 200)"


def step_login(phone, password, partner):
    """HAR Entry 274 - POST /user/login/account
    Body: {account, password}
    Response: {"code":200, "token":"..."}
    """
    body = {"account": phone, "password": password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body, partner=partner)
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login \u2705"


def step_check_regist_gifts(token, partner):
    """HAR Entry 280 - GET /opendata/homepage/registGifts
    Response: {"code":200,"data":{"claimed":false,"config":{"items":[{"id":"freespinbet10","num":10}]}}}
    """
    status, resp = call_api("GET", H5_HOST, PATH_REGIST_GIFTS, token=token, partner=partner)
    if status != 200:
        return False, "Gift status FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Gift status FAIL: {}".format(resp)
    data = resp.get("data", {})
    claimed = data.get("claimed")
    return True, "Gift status OK (claimed={})".format(claimed)


def step_homepage_index_v4(token, partner):
    """HAR Entry 286 - POST /opendata/homepage/indexV4
    Body: {} (HAR proves bodySize=2, text='{}')
    """
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Homepage FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Homepage FAIL: {}".format(resp)
    return True, "Homepage config OK \u2705"


def step_get_free_package(token, partner):
    """HAR Entry 283 - POST /user/profile/getfreepackage  (before claim)
    Body: {} (HAR proves bodySize=2, text='{}')
    Response before claim: {"code":200,"freePackage":{},"confs":{}}
    KEY FIX: uses `access-token` header, NOT `Authorization: Bearer`
    """
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Free package FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Free package FAIL: {}".format(resp)
    return True, "Free package OK \u2705 (before claim)"


def step_claim_gift(token, partner):
    """HAR Entry 288 - POST /user/profile/claimRegistGifts
    Body: {} (HAR proves bodySize=2, text='{}')
    Response: {"code":200,"items":[{"id":"freespinbet10","num":10}]}
    """
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Claim gift FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Claim gift FAIL: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM
               for i in items)
    if not found:
        return False, "Gift mismatch: {}".format(items)
    return True, "Gift claimed \u2705 freespinbet10 x10"


def step_get_free_package_after_claim(token, partner):
    """HAR Entry 293 - POST /user/profile/getfreepackage  (after claim)
    Body: {} (HAR proves bodySize=2, text='{}')
    Response: {"code":200,"freePackage":{"freespinbet10":10},"confs":{...}}
    """
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Free package (after) FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Free package (after) FAIL: {}".format(resp)
    free_pkg = resp.get("freePackage", {})
    if EXPECTED_GIFT_ID in free_pkg:
        return True, "Free package verified \u2705 freespinbet10={}x".format(free_pkg[EXPECTED_GIFT_ID])
    return True, "Free package after claim: {}".format(free_pkg)


def step_set_language(token, partner):
    """HAR Entry 298 - POST /user/profile/setlanguage
    Body: {"language":"en-US"}
    """
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner)
    if status != 200:
        return False, "Set language FAIL: HTTP {}".format(status)
    if resp.get("code") != 200:
        return False, "Set language FAIL: {}".format(resp)
    return True, "Language set \u2705 (en-US)"


def step_freespin_subscribe(token):
    """HAR Entry 618 - POST /freetinygames/freespin/subscribe
    Body: {"tyid":"freespinbet10"}
    Uses GAME host with game-specific headers.
    """
    body = {"tyid": SUBSCRIBE_TYID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: {}".format(resp)
    return True, "Subscribed \u2705 (freespinbet10)"


def step_play_spins(token):
    """HAR Entries 624-651 - POST /freetinygames/freespin/bet
    10 calls. Body: {} (HAR proves bodySize=2, text='{}').
    Response has tycount (remaining spins): 9,8,7,...,0.
    Uses GAME host with game-specific headers.
    """
    results = []
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body={}, token=token, game=True)
        if status != 200:
            results.append("Spin {}: \u274c HTTP {}".format(i+1, status))
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

    # Step 0 - Follow short link, extract partner
    report.append("\U0001f3b0 BetFugu Auto-Register")
    report.append("Refer link: {}".format(refer_link))
    partner, user_id, redirect_url = follow_short_link_and_get_partner(refer_link)
    if not partner:
        report.append("\u274c Partner extract FAIL: {}".format(redirect_url))
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

    # Step 1 - Register
    ok, msg = step_register(phone, password, partner)
    report.append("1\ufe0f\u20e3 Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 2 - Login
    token, msg = step_login(phone, password, partner)
    report.append("2\ufe0f\u20e3 Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    # Step 3 - Check gift status
    ok, msg = step_check_regist_gifts(token, partner)
    report.append("3\ufe0f\u20e3 Gift status: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 4 - Homepage config
    ok, msg = step_homepage_index_v4(token, partner)
    report.append("4\ufe0f\u20e3 Homepage: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 5 - Free package check (before claim)
    ok, msg = step_get_free_package(token, partner)
    report.append("5\ufe0f\u20e3 Free package (pre): {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 6 - Claim gift
    ok, msg = step_claim_gift(token, partner)
    report.append("6\ufe0f\u20e3 Claim gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 7 - Free package check (after claim)
    ok, msg = step_get_free_package_after_claim(token, partner)
    report.append("7\ufe0f\u20e3 Free package (post): {}".format(msg))

    # Step 8 - Set language
    ok, msg = step_set_language(token, partner)
    report.append("8\ufe0f\u20e3 Language: {}".format(msg))

    # Step 9 - Subscribe to free spin
    ok, msg = step_freespin_subscribe(token)
    report.append("9\ufe0f\u20e3 Subscribe: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 10 - Play 10 free spins
    report.append("\U0001f51f Playing 10 free spins...")
    ok, spin_report = step_play_spins(token)
    report.append(spin_report)
    report.append("")
    report.append("\u2705 Done! Registration + 10 free spins complete.")

    return True, "\n".join(report)


# ---- Telegram Bot Commands ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f3b0 *BetFugu Auto-Register Bot*\n\n"
        "HAR-verified \u2014 no guessing.\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` \u2014 refer link do, bot auto register + 10 free spins kheliga\n"
        "`/help` \u2014 help\n\n"
        "Example:\n"
        "`/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /register <REFER_LINK>
    Refer link format: https://s.betfugu01.com/xxxxx
    Bot follows 302 redirect -> extracts partner -> registers -> plays spins.
    """
    if not context.args:
        await update.message.reply_text(
            "\u26a0\ufe0f Refer link do!\n\n"
            "Use: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
            parse_mode="Markdown",
        )
        return

    refer_link = " ".join(context.args)

    msg = await update.message.reply_text(
        "\U0001f504 Processing refer link...\n{}".format(refer_link)
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
        "\U0001f4d6 *Help*\n\n"
        "`/register <REFER_LINK>` \u2014 auto register + 10 free spins\n\n"
        "Bot kya karta hai:\n"
        "\u2022 Short refer link follow -> 302 redirect -> partner code extract\n"
        "\u2022 Random 10-digit phone (6/7/8/9 se start)\n"
        "\u2022 Password: 123456\n"
        "\u2022 Register -> Login -> Gift check -> Homepage -> Free pkg -> Claim -> Play 10 spins\n\n"
        "Example:\n"
        "`/register https://s.betfugu01.com/ezzwvl51eipuy39`\n\n"
        "HAR-verified headers (key fix):\n"
        "\u2022 access-token header (NOT Authorization: Bearer)\n"
        "\u2022 25+ custom headers: appid, channel, currency, version, partner...\n"
        "\u2022 body={} for all POST calls",
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
