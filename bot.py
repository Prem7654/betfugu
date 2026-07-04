#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, header, body from original HAR file (1037 entries).

KEY FIXES (all HAR-verified from 2nd HAR file):
1. Server uses `access-token` custom header (NOT `Authorization: Bearer`).
2. All 25+ custom headers from HAR included.
3. Body is always `{}` for POST calls (HAR: bodySize=2, text='{}').
4. Password is AES-256-CBC encrypted (HAR + JS source verified).
5. REFER BONUS FIX: sourceurl must contain pwa_uuid!
   - HAR proves: register sourceurl has `&pwa_uuid=xxx` appended
   - Without pwa_uuid, server cannot link browser session to referral
   - HAR Entry 633 sourceurl: ...&partner=66666666&rtm=1783147761401&pwa_uuid=29fbe91f3451e28ac1be0a6c4c7ede95#/login
   - Bot was sending: ...&partner=66666666&rtm=xxx#/  (MISSING pwa_uuid!)
6. isfrom: "other_h5" for register (HAR shows other_h5, not other_pwa)
7. Pre-login calls: indexV4, getdaylyjackpot, gameConfigs, itemConfig — ALL with referral sourceurl

HAR PROOF of refer bonus:
  Entry 284 (before refer): earn/statsV2 -> current:20, today:20, users:2
  Entry 1010 (after refer): earn/statsV2 -> current:30, today:30, users:3
  Entry 1022: earn/detail -> uid:2712722, bindtime:2026-07-04T08:50:37, finish:true
  => 20 -> 30 = +10 refer bonus! Server auto-credits when partner code in register + pwa_uuid in sourceurl.

AES encryption (from JS source, HAR-verified):
  key = "3dfe30508ab4a03043f014a6684034ff" (32 bytes UTF-8)
  iv  = "fe3480b3543dytj3" (16 bytes UTF-8)
  pureKey = "WXNyfgYJffWxZm0bly3nts1/..." (decrypted to get encryptKey:encryptIv)
  encryptKey = "34d80508ab4a03043f014a66840ba23w" (32 bytes)
  encryptIv  = "585280b3543d2d89" (16 bytes)
  AES.encrypt("123456") = "h1glmyQ2dTe2r+ARoXsgbQ==" (HAR verified!)

Flow (all HAR-verified from 1037-entry HAR):
  0. Follow short refer link -> 302 redirect -> extract partner + userId + rtm
  0a. Generate pwa_uuid (random 32-char hex)
  0b. Pre-login calls with referral sourceurl (userId + pwa_uuid):
      - POST /client/log (web_open event with pwa_uuid)
      - POST /opendata/homepage/indexV4 (referral tracking)
      - POST /opendata/getdaylyjackpot
      - GET  /opendata/gameConfigs
      - POST /opendata/itemConfig (sourceurl has #/login)
  1. Generate random Indian phone (starts 6/7/8/9, 10 digits)
  2. AES encrypt password
  3. Register: POST /user/register/account (partner, itemuserfor=freespin, sourceurl has pwa_uuid + #/login)
  4. Login: POST /user/login/account (sourceurl has pwa_uuid + #/login)
  5. Gift status -> claim gift -> play spins, etc.

Env:
  BOT_TOKEN  — Telegram bot token from @BotFather
"""

import os
import re
import json
import random
import time
import uuid
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
_AES_ENCRYPT_KEY = b"34d80508ab4a03043f014a66840ba23w"  # 32 bytes
_AES_ENCRYPT_IV = b"585280b3543d2d89"                     # 16 bytes


def aes_encrypt(plaintext):
    """AES-256-CBC encrypt with PKCS7 padding (HAR + JS verified).
    HAR proof: aes_encrypt("123456") == "h1glmyQ2dTe2r+ARoXsgbQ=="
    """
    key = _AES_ENCRYPT_KEY
    iv = _AES_ENCRYPT_IV
    data = plaintext.encode("utf-8")

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
    raise RuntimeError("AES encryption failed")


# ---- Verified constants (from 1037-entry HAR) ----
H5_HOST = "https://h5server.betfuguapi.com"
GAME_HOST = "https://game.betfuguapi.com"

PATH_REGISTER = "/user/register/account"
PATH_LOGIN = "/user/login/account"
PATH_REGIST_GIFTS = "/opendata/homepage/registGifts"
PATH_INDEX_V4 = "/opendata/homepage/indexV4"
PATH_GET_FREEPACKAGE = "/user/profile/getfreepackage"
PATH_CLAIM_GIFT = "/user/profile/claimRegistGifts"
PATH_SET_LANGUAGE = "/user/profile/setlanguage"
PATH_GAME_CONFIGS = "/opendata/gameConfigs"
PATH_DAYLY_JACKPOT = "/opendata/getdaylyjackpot"
PATH_ITEM_CONFIG = "/opendata/itemConfig"
PATH_CLIENT_LOG = "/client/log"
PATH_FREESPIN_SUBSCRIBE = "/freetinygames/freespin/subscribe"
PATH_FREESPIN_BET = "/freetinygames/freespin/bet"

VERIFIED_ITEMUSERFOR = "freespin"
EXPECTED_GIFT_ID = "freespinbet10"
EXPECTED_GIFT_NUM = 10
SUBSCRIBE_TYID = "freespinbet10"
NUM_SPINS = 10
FIXED_PASSWORD = "123456"
SET_LANGUAGE = "en-US"

# HAR-verified visitorid (from Entry 633 register call)
HAR_VISITOR_ID = "MB==d9f771e6f02f464acd2a8ae95601599ff40dfc88202627"


def generate_pwa_uuid():
    """Generate random 32-char hex string (like HAR pwa_uuid)."""
    return uuid.uuid4().hex


def build_sourceurl(user_id, partner, rtm, pwa_uuid, fragment="#/"):
    """Build HAR-verified sourceurl with userId + pwa_uuid.
    HAR proof (Entry 633 register):
      https://betfugu02.com/bf_pwa/index.html?userId=2335316&cury=INR&partner=66666666&rtm=1783147761401&pwa_uuid=29fbe91f...#/login
    """
    base = "https://betfugu02.com/bf_pwa/index.html?"
    params = "cury=INR&partner={}&rtm={}".format(partner, rtm)
    if user_id and user_id != "undefined":
        params = "userId={}&".format(user_id) + params
    if pwa_uuid:
        params += "&pwa_uuid={}".format(pwa_uuid)
    return base + params + fragment


# ---- HAR-verified headers for H5 host ----
def make_h5_headers(token=None, partner=None, sourceurl=None, isfrom="other_pwa"):
    """Build HAR-verified H5 headers.
    KEY: isfrom=other_h5 for register/login (HAR Entry 633), other_pwa for normal calls.
    """
    headers = {
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
        "isfrom": isfrom,
        "ispwa": "true",
        "webfonts": "Microsoft YaHei",
        "deviceid": "",
        "visitorid": HAR_VISITOR_ID,
        "sourceurl": sourceurl or "https://betfugu02.com/bf_pwa/index.html#/",
        "webrtc": "",
        "trackertoken": "",
        "trackername": "",
    }
    if partner:
        headers["partner"] = str(partner)
    if token:
        headers["access-token"] = token
    return headers


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


def call_api(method, host, path, body=None, token=None, partner=None, game=False, sourceurl=None, isfrom="other_pwa"):
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
        headers = make_h5_headers(token=token, partner=partner, sourceurl=sourceurl, isfrom=isfrom)

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
    """Follow short refer link -> 302 redirect -> extract partner + userId + rtm."""
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


# ---- BetFugu API steps (all HAR-verified from 1037-entry HAR) ----

def step_client_log_web_open(pwa_uuid, partner, sourceurl):
    """HAR Entry 544 - POST /client/log (web_open event with pwa_uuid).
    This registers the browser session with the server BEFORE register.
    """
    body = {
        "logname": "pwa_log",
        "event": "web_open",
        "content": {"pwa_uuid": pwa_uuid}
    }
    status, resp = call_api("POST", H5_HOST, PATH_CLIENT_LOG, body=body,
                           partner=partner, sourceurl=sourceurl)
    return status == 200, "web_open logged"


def step_prelogin_index_v4(partner, sourceurl):
    """HAR Entry 561 - POST /opendata/homepage/indexV4 (BEFORE register, NO token).
    Referral tracking call. sourceurl MUST contain userId + pwa_uuid.
    """
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={},
                           partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "indexV4 FAIL: {}".format(resp)
    return True, "indexV4 OK"


def step_prelogin_dayly_jackpot(partner, sourceurl):
    """HAR Entry 559 - POST /opendata/getdaylyjackpot"""
    body = {"id": "daylyJackpot", "version": "1"}
    status, resp = call_api("POST", H5_HOST, PATH_DAYLY_JACKPOT, body=body,
                           partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "daylyJackpot FAIL"
    return True, "daylyJackpot OK"


def step_prelogin_game_configs(partner, sourceurl):
    """HAR Entry 578 - GET /opendata/gameConfigs"""
    status, resp = call_api("GET", H5_HOST, PATH_GAME_CONFIGS,
                           partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "gameConfigs FAIL"
    return True, "gameConfigs OK"


def step_prelogin_item_config(partner, sourceurl):
    """HAR Entry 596 - POST /opendata/itemConfig (sourceurl has #/login)"""
    status, resp = call_api("POST", H5_HOST, PATH_ITEM_CONFIG, body={},
                           partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "itemConfig FAIL"
    return True, "itemConfig OK"


def step_register(phone, encrypted_password, partner, sourceurl):
    """HAR Entry 633 - POST /user/register/account
    Body: {account, password(AES-encrypted), partner, itemuserfor:"freespin"}
    KEY: sourceurl MUST contain userId + pwa_uuid + #/login
    KEY: isfrom must be "other_h5" (HAR verified, NOT other_pwa)
    """
    body = {
        "account": phone,
        "password": encrypted_password,
        "partner": int(partner),
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body,
                           partner=partner, sourceurl=sourceurl, isfrom="other_h5")
    if status != 200 or resp.get("code") != 200:
        return False, "Register FAIL: {}".format(resp)
    return True, "Registered \u2705"


def step_login(phone, encrypted_password, partner, sourceurl):
    """HAR Entry 636 - POST /user/login/account
    Body: {account, password(AES-encrypted)}
    KEY: sourceurl MUST contain userId + pwa_uuid + #/login
    KEY: isfrom must be "other_h5" (HAR verified)
    """
    body = {"account": phone, "password": encrypted_password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body,
                           partner=partner, sourceurl=sourceurl, isfrom="other_h5")
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login \u2705"


def step_check_regist_gifts(token, partner, sourceurl):
    """HAR Entry 642 - GET /opendata/homepage/registGifts"""
    status, resp = call_api("GET", H5_HOST, PATH_REGIST_GIFTS, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "Gift status FAIL"
    if resp.get("code") != 200:
        return False, "Gift status FAIL: {}".format(resp)
    return True, "Gift status OK"


def step_homepage_index_v4(token, partner, sourceurl):
    """HAR Entry 649 - POST /opendata/homepage/indexV4 (post-login)"""
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Homepage FAIL"
    return True, "Homepage OK \u2705"


def step_get_free_package(token, partner, sourceurl):
    """HAR Entry 646 - POST /user/profile/getfreepackage (before claim)"""
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Free package FAIL"
    return True, "Free package OK \u2705"


def step_claim_gift(token, partner, sourceurl):
    """HAR Entry 651 - POST /user/profile/claimRegistGifts"""
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Claim gift FAIL: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM for i in items)
    if not found:
        return False, "Gift mismatch: {}".format(items)
    return True, "Gift claimed \u2705 freespinbet10 x10"


def step_get_free_package_after_claim(token, partner, sourceurl):
    """HAR Entry 654 - POST /user/profile/getfreepackage (after claim)"""
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "Free package (after) FAIL"
    free_pkg = resp.get("freePackage", {})
    if EXPECTED_GIFT_ID in free_pkg:
        return True, "Free package verified \u2705 {}x".format(free_pkg[EXPECTED_GIFT_ID])
    return True, "Free package: {}".format(free_pkg)


def step_set_language(token, partner, sourceurl):
    """HAR Entry 661 - POST /user/profile/setlanguage"""
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Set language FAIL"
    return True, "Language set \u2705"


def step_freespin_subscribe(token):
    """HAR Entry 913 - POST /freetinygames/freespin/subscribe"""
    body = {"tyid": SUBSCRIBE_TYID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: {}".format(resp)
    return True, "Subscribed \u2705"


def step_play_spins(token):
    """HAR Entries 915-927 - POST /freetinygames/freespin/bet (10 calls)"""
    results = []
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body={}, token=token, game=True)
        if status != 200:
            results.append("Spin {}: \u274c HTTP {}".format(i+1, status))
            break
        game_data = resp.get("data", {})
        balance = game_data.get("balance", "?")
        win = game_data.get("win", 0)
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        results.append("Spin {}/{}: win={} bal={} left={}".format(i+1, NUM_SPINS, win, balance, tycount))
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
    report.append("Partner: {}".format(partner))
    if user_id:
        report.append("Referrer userId: {}".format(user_id))
    report.append("")

    # Generate pwa_uuid (HAR-verified: server uses this to link session to referral)
    pwa_uuid = generate_pwa_uuid()
    report.append("pwa_uuid: {}".format(pwa_uuid))

    # Build HAR-verified sourceurl with userId + pwa_uuid (KEY FIX!)
    src_home = build_sourceurl(user_id, partner, rtm, pwa_uuid, "#/")
    src_login = build_sourceurl(user_id, partner, rtm, pwa_uuid, "#/login")

    phone = generate_random_phone()
    password = FIXED_PASSWORD
    report.append("Phone: {}".format(phone))
    report.append("Password: {} (AES encrypted)".format(password))
    report.append("")

    # Step 0a - Pre-login: client/log web_open (HAR Entry 544)
    ok, msg = step_client_log_web_open(pwa_uuid, partner, src_home)
    report.append("0\ufe0f\u20e3 web_open log: {}".format(msg))

    # Step 0b - Pre-login: indexV4 (HAR Entry 561)
    ok, msg = step_prelogin_index_v4(partner, src_home)
    report.append("0\ufe0f\u20e3 indexV4 (referral): {}".format(msg))

    # Step 0c - Pre-login: daylyJackpot (HAR Entry 559)
    ok, msg = step_prelogin_dayly_jackpot(partner, src_home)
    report.append("0\ufe0f\u20e3 daylyJackpot: {}".format(msg))

    # Step 0d - Pre-login: gameConfigs (HAR Entry 578)
    ok, msg = step_prelogin_game_configs(partner, src_home)
    report.append("0\ufe0f\u20e3 gameConfigs: {}".format(msg))

    # Step 0e - Pre-login: itemConfig (HAR Entry 596, sourceurl #/login)
    ok, msg = step_prelogin_item_config(partner, src_login)
    report.append("0\ufe0f\u20e3 itemConfig: {}".format(msg))
    report.append("")

    # AES encrypt password (HAR verified!)
    try:
        encrypted_password = aes_encrypt(password)
        report.append("AES encrypt: \u2705 {}...".format(encrypted_password[:20]))
    except Exception as e:
        report.append("AES encrypt: \u274c FAIL: {}".format(e))
        return False, "\n".join(report)
    report.append("")

    # Step 1 - Register (with AES-encrypted password + pwa_uuid in sourceurl + isfrom=other_h5)
    ok, msg = step_register(phone, encrypted_password, partner, src_login)
    report.append("1\ufe0f\u20e3 Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    time.sleep(0.5)

    # Step 2 - Login (with same sourceurl + isfrom=other_h5)
    token, msg = step_login(phone, encrypted_password, partner, src_login)
    report.append("2\ufe0f\u20e3 Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    # Post-login sourceurl (still has userId + pwa_uuid + #/)
    src_post = build_sourceurl(user_id, partner, rtm, pwa_uuid, "#/")

    # Step 3 - Check gift status
    ok, msg = step_check_regist_gifts(token, partner, src_post)
    report.append("3\ufe0f\u20e3 Gift status: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 4 - Free package check
    ok, msg = step_get_free_package(token, partner, src_post)
    report.append("4\ufe0f\u20e3 Free package (pre): {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 5 - Homepage config
    ok, msg = step_homepage_index_v4(token, partner, src_post)
    report.append("5\ufe0f\u20e3 Homepage: {}".format(msg))

    # Step 6 - Claim gift
    ok, msg = step_claim_gift(token, partner, src_post)
    report.append("6\ufe0f\u20e3 Claim gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    # Step 7 - Free package after claim
    ok, msg = step_get_free_package_after_claim(token, partner, src_post)
    report.append("7\ufe0f\u20e3 Free package (post): {}".format(msg))

    # Step 8 - Set language
    ok, msg = step_set_language(token, partner, src_post)
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
    report.append("\U0001f4b0 Refer bonus should be credited to referrer! (HAR verified: 20->30)")

    return True, "\n".join(report)


# ---- Telegram Bot Commands ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f3b0 *BetFugu Auto-Register Bot*\n\n"
        "HAR-verified \u2014 no guessing.\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` \u2014 refer link do, bot auto register + 10 free spins\n"
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
        "\u2022 Short refer link follow -> 302 redirect -> partner + userId + rtm extract\n"
        "\u2022 pwa_uuid generate -> session link to referral\n"
        "\u2022 Pre-login: web_open log, indexV4, jackpot, gameConfigs, itemConfig\n"
        "\u2022 Password AES-256-CBC encrypted (HAR verified)\n"
        "\u2022 Random phone (6/7/8/9 start)\n"
        "\u2022 Register -> Login -> Gift -> Claim -> 10 spins\n\n"
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
