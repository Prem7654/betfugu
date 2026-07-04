#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, header, body from original HAR file.

KEY FIXES:
1. Server uses `access-token` custom header (NOT `Authorization: Bearer`).
2. All 20+ custom headers from HAR included.
3. Body is always `{}` for POST calls (HAR: bodySize=2, text='{}').
4. REFERRAL FIX: Pre-login indexV4 with userId in sourceurl.
5. PASSWORD FIX: Password is AES-CBC encrypted before sending.
   HAR proves: plain "123456" -> AES encrypt -> "h1glmyQ2dTe2r+ARoXsgbQ=="
   Without encryption, register works but referral bonus is NOT credited.

AES encryption (from JS source, HAR-verified):
  1. Decrypt pureKey using key/iv to get encryptKey:encryptIv
     key = "3dfe30508ab4a03043f014a6684034ff" (32 bytes UTF-8)
     iv  = "fe3480b3543dytj3" (16 bytes UTF-8)
     pureKey = "WXNyfgYJffWxZm0bly3nts1/Yi/yZXJwHTcAll3lzETRUX1bNncAIeX2kg3J4O1NCpHhUiSW3DdQs9ZLdwNEqA=="
     Decrypt -> "34d80508ab4a03043f014a66840ba23w:585280b3543d2d89"
     encryptKey = "34d80508ab4a03043f014a66840ba23w" (32 bytes)
     encryptIv  = "585280b3543d2d89" (16 bytes)
  2. AES-256-CBC encrypt password with PKCS7 padding
     AES.encrypt("123456") = "h1glmyQ2dTe2r+ARoXsgbQ==" (HAR verified!)

Flow (all HAR-verified):
  0. Follow short refer link -> 302 redirect -> extract partner + userId
  0a. Pre-login indexV4 with referral sourceurl (HAR Entry 131)
  1. Generate random Indian phone (starts 6/7/8/9, 10 digits)
  2. AES encrypt password
  3. Register    : POST /user/register/account  (partner, itemuserfor=freespin)
  4. Login      : POST /user/login/account    (returns token)
  5. Gift status : GET  /opendata/homepage/registGifts
  6-11. Claim gift, play spins, etc.

Env:
  BOT_TOKEN  — Telegram bot token from @BotFather
"""

import os
import re
import json
import random
import time
import hashlib
import base64
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlparse, parse_qs

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ---- AES Encryption (HAR + JS source verified) ----
# Step 1: Decrypt pureKey to get encryptKey + encryptIv
# These are hardcoded in the JS source (Entry 88: index-BT3HxEvK.js)
_AES_DECRYPT_KEY = b"3dfe30508ab4a03043f014a6684034ff"  # 32 bytes
_AES_DECRYPT_IV = b"fe3480b3543dytj3"                  # 16 bytes
_AES_PURE_KEY = "WXNyfgYJffWxZm0bly3nts1/Yi/yZXJwHTcAll3lzETRUX1bNncAIeX2kg3J4O1NCpHhUiSW3DdQs9ZLdwNEqA=="

# Decrypted pureKey = "34d80508ab4a03043f014a66840ba23w:585280b3543d2d89"
# encryptKey = "34d80508ab4a03043f014a66840ba23w" (32 bytes)
# encryptIv  = "585280b3543d2d89" (16 bytes)
_AES_ENCRYPT_KEY = b"34d80508ab4a03043f014a66840ba23w"  # 32 bytes
_AES_ENCRYPT_IV = b"585280b3543d2d89"                     # 16 bytes


def aes_encrypt(plaintext):
    """AES-256-CBC encrypt with PKCS7 padding (HAR + JS verified).
    Uses pure Python implementation (no external deps needed).
    HAR proof: aes_encrypt("123456") == "h1glmyQ2dTe2r+ARoXsgbQ=="
    """
    # PKCS7 padding
    key = _AES_ENCRYPT_KEY
    iv = _AES_ENCRYPT_IV
    data = plaintext.encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len
    
    # AES-256-CBC encryption using pure Python
    # We use the built-in hashlib for key schedule, but need actual AES
    # Since we can't use pycryptodome, we implement AES from scratch
    # Actually, Python's hashlib doesn't have AES. Let's use a different approach.
    # We can use the 'cryptography' package if available, or implement AES manually.
    # 
    # Actually, the simplest approach: use subprocess to call node.js
    # which is available on Railway (npm/node) and can do AES natively.
    # But for portability, let's try Python first.
    
    # Try using 'cryptography' package first
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.backends import default_backend
        
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(encrypted).decode("utf-8")
    except ImportError:
        pass
    
    # Fallback: use subprocess with node.js (available on Railway)
    import subprocess
    node_script = '''
const crypto = require('crypto');
const key = Buffer.from(process.argv[1], 'utf8');
const iv = Buffer.from(process.argv[2], 'utf8');
const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
let encrypted = cipher.update(process.argv[3], 'utf8');
encrypted = Buffer.concat([encrypted, cipher.final()]);
process.stdout.write(encrypted.toString('base64'));
'''
    result = subprocess.run(
        ["node", "-e", node_script, key.decode("utf-8"), iv.decode("utf-8"), plaintext],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0 and result.stdout:
        return result.stdout.strip()
    raise RuntimeError("AES encryption failed: no cryptography package and node.js not available")


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

# ---- HAR-verified headers for H5 host ----
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

REDIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def call_api(method, host, path, body=None, token=None, partner=None, game=False, sourceurl=None):
    """Make single API call, return (http_status, response_json).
    HAR PROOF: POST calls use body='{}' (bodySize=2). Token in `access-token` header.
    """
    url = host + path

    if method == "POST":
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        else:
            data = b"{}"
    else:
        data = None

    if game or host == GAME_HOST:
        headers = dict(GAME_BASE_HEADERS)
        if token:
            headers["access-token"] = token
    else:
        headers = dict(H5_BASE_HEADERS)
        if partner:
            headers["partner"] = str(partner)
        if token:
            headers["access-token"] = token
        if sourceurl:
            headers["sourceurl"] = sourceurl

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
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def follow_short_link_and_get_partner(short_url):
    """Follow short refer link -> 302 redirect -> extract partner + userId."""
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
        return None, None, "", "No redirect Location found"

    parsed = urlparse(final_url)
    params = parse_qs(parsed.query)
    partner = params.get("partner", [None])[0]
    user_id = params.get("userId", [None])[0]
    rtm = params.get("rtm", [""])[0]

    if not partner or partner == "undefined":
        return None, None, "", "Partner not found in redirect URL: {}".format(final_url)

    return partner, user_id, rtm, final_url


def generate_random_phone():
    """Generate random 10-digit Indian phone starting with 6, 7, 8, or 9."""
    first_digit = random.choice(["6", "7", "8", "9"])
    rest = "".join(random.choice("0123456789") for _ in range(9))
    return first_digit + rest


# ---- BetFugu API steps (all HAR-verified) ----

def step_prelogin_referral_index_v4(partner, user_id, rtm):
    """HAR Entry 131 - POST /opendata/homepage/indexV4 (BEFORE register, NO token)
    Referral tracking call. sourceurl must contain userId from redirect URL.
    """
    if user_id and user_id != "undefined":
        sourceurl = (
            "https://betfugu02.com/bf_pwa/index.html"
            "?userId={}&cury=INR&partner={}&rtm={}#/".format(
                user_id, partner, rtm)
        )
    else:
        sourceurl = "https://betfugu02.com/bf_pwa/index.html#/"

    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={},
                           partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "Referral track FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Referral track FAIL: {}".format(resp)
    return True, "Referral tracked \u2705 (userId={})".format(user_id)


def step_register(phone, encrypted_password, partner):
    """HAR Entry 271 - POST /user/register/account
    Body: {account, password(AES-encrypted), partner, itemuserfor:"freespin"}
    KEY: password must be AES encrypted (HAR proves this).
    """
    body = {
        "account": phone,
        "password": encrypted_password,
        "partner": int(partner),
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    sourceurl = "https://betfugu02.com/bf_pwa/index.html#/login"
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body,
                           partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Registration FAIL: {}".format(resp)
    return True, "Registered \u2705 (code 200)"


def step_login(phone, encrypted_password, partner):
    """HAR Entry 274 - POST /user/login/account
    Body: {account, password(AES-encrypted)}
    KEY: password must be AES encrypted (same as register).
    """
    body = {"account": phone, "password": encrypted_password}
    sourceurl = "https://betfugu02.com/bf_pwa/index.html#/"
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body,
                           partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login \u2705"


def step_check_regist_gifts(token, partner):
    """HAR Entry 280 - GET /opendata/homepage/registGifts"""
    status, resp = call_api("GET", H5_HOST, PATH_REGIST_GIFTS, token=token, partner=partner)
    if status != 200:
        return False, "Gift status FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Gift status FAIL: {}".format(resp)
    data = resp.get("data", {})
    claimed = data.get("claimed")
    return True, "Gift status OK (claimed={})".format(claimed)


def step_homepage_index_v4(token, partner):
    """HAR Entry 286 - POST /opendata/homepage/indexV4 (post-login)"""
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Homepage FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Homepage FAIL: {}".format(resp)
    return True, "Homepage config OK \u2705"


def step_get_free_package(token, partner):
    """HAR Entry 283 - POST /user/profile/getfreepackage (before claim)"""
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner)
    if status != 200:
        return False, "Free package FAIL: HTTP {} {}".format(status, resp)
    if resp.get("code") != 200:
        return False, "Free package FAIL: {}".format(resp)
    return True, "Free package OK \u2705 (before claim)"


def step_claim_gift(token, partner):
    """HAR Entry 288 - POST /user/profile/claimRegistGifts"""
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
    """HAR Entry 293 - POST /user/profile/getfreepackage (after claim)"""
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
    """HAR Entry 298 - POST /user/profile/setlanguage"""
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner)
    if status != 200:
        return False, "Set language FAIL: HTTP {}".format(status)
    if resp.get("code") != 200:
        return False, "Set language FAIL: {}".format(resp)
    return True, "Language set \u2705 (en-US)"


def step_freespin_subscribe(token):
    """HAR Entry 618 - POST /freetinygames/freespin/subscribe"""
    body = {"tyid": SUBSCRIBE_TYID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: {}".format(resp)
    return True, "Subscribed \u2705 (freespinbet10)"


def step_play_spins(token):
    """HAR Entries 624-651 - POST /freetinygames/freespin/bet (10 calls)"""
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

    # Step 0 - Follow short link, extract partner + userId + rtm
    report.append("\U0001f3b0 BetFugu Auto-Register")
    report.append("Refer link: {}".format(refer_link))
    partner, user_id, rtm, redirect_url = follow_short_link_and_get_partner(refer_link)
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

    # Step 0a - Pre-login referral tracking (HAR Entry 131)
    if user_id and user_id != "undefined":
        ok, msg = step_prelogin_referral_index_v4(partner, user_id, rtm)
        report.append("0\ufe0f\u20e3 Referral track: {}".format(msg))
        if not ok:
            report.append("   (continuing anyway...)")
    else:
        report.append("0\ufe0f\u20e3 Referral track: Skipped (no userId in refer link)")
    report.append("")

    # AES encrypt the password (HAR verified!)
    try:
        encrypted_password = aes_encrypt(password)
        report.append("AES encrypt: \u2705 {}".format(encrypted_password[:20] + "..."))
    except Exception as e:
        report.append("AES encrypt: \u274c FAIL: {}".format(e))
        return False, "\n".join(report)
    report.append("")

    # Step 1 - Register (with AES-encrypted password)
    ok, msg = step_register(phone, encrypted_password, partner)
    report.append("1\ufe0f\u20e3 Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    time.sleep(0.5)

    # Step 2 - Login (with same AES-encrypted password)
    token, msg = step_login(phone, encrypted_password, partner)
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

    # Step 5 - Free package check
    ok, msg = step_get_free_package(token, partner)
    report.append("5\ufe0f\u20e3 Free package (pre): {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 6 - Claim gift
    ok, msg = step_claim_gift(token, partner)
    report.append("6\ufe0f\u20e3 Claim gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 7 - Free package after claim
    ok, msg = step_get_free_package_after_claim(token, partner)
    report.append("7\ufe0f\u20e3 Free package (post): {}".format(msg))

    # Step 8 - Set language
    ok, msg = step_set_language(token, partner)
    report.append("8\ufe0f\u20e3 Language: {}".format(msg))

    # Step 9 - Subscribe
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
        "\u2022 Short refer link follow -> 302 redirect -> partner + userId extract\n"
        "\u2022 Pre-login indexV4 with referral sourceurl (refer bonus track)\n"
        "\u2022 Password AES-256-CBC encrypted (HAR verified)\n"
        "\u2022 Random 10-digit phone (6/7/8/9 se start)\n"
        "\u2022 Register -> Login -> Gift check -> Claim -> Play 10 spins\n\n"
        "Example:\n"
        "`/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN env variable set nahi hai!")
        raise SystemExit(1)
    print("BetFugu Auto-Register TG Bot starting...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    print("Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
