#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot — Telegram + HAR-verified.
No guessing. Every endpoint, header, body from original HAR file (1037 entries).

KEY FIXES (all HAR-verified):
1. access-token custom header (NOT Authorization: Bearer).
2. All 25+ custom headers from HAR included.
3. Body is always `{}` for POST calls.
4. Password AES-256-CBC encrypted (HAR + JS verified).
5. pwa_uuid in sourceurl (after pwa_download, not in first calls).
6. isfrom: "other_h5" for ALL H5 calls.
7. webrtc header: real IP.
8. Spin response: lotteryGameResult.data.balance/win (HAR verified).
9. Pre-login sequence: web_open, daylyJackpot, indexV4, pwa_download, indexV4(2), daylyJackpot(2), gameConfigs, itemConfig.

HAR PROOF of refer bonus:
  Entry 284 (before): earn/statsV2 -> current:20, users:2
  Entry 1010 (after): earn/statsV2 -> current:30, users:3
  => +10 per registration.

HAR spin response format (Entry 915):
  {"code":200,"lotteryGameResult":{"code":200,"message":"SUCCESS","data":{"balance":8,"bet":10,"win":8,...}},"tycount":9}
  => data is inside lotteryGameResult.data, NOT top-level data.
"""

import os
import re
import json
import random
import time
import uuid
import base64
import socket
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
_AES_ENCRYPT_KEY = b"34d80508ab4a03043f014a66840ba23w"
_AES_ENCRYPT_IV = b"585280b3543d2d89"


def aes_encrypt(plaintext):
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
HAR_VISITOR_ID = "MB==d9f771e6f02f464acd2a8ae95601599ff40dfc88202627"


_SERVER_IP = None

def get_webrtc_ip():
    global _SERVER_IP
    if _SERVER_IP is None:
        try:
            req = urllib.request.Request("https://api.ipify.org?format=text",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                _SERVER_IP = resp.read().decode("utf-8").strip()
        except Exception:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                _SERVER_IP = s.getsockname()[0]
                s.close()
            except Exception:
                _SERVER_IP = ""
        print("Server IP: {}".format(_SERVER_IP))
    return _SERVER_IP


def generate_pwa_uuid():
    return uuid.uuid4().hex


def build_sourceurl(user_id, partner, rtm, pwa_uuid=None, fragment="#/"):
    base = "https://betfugu02.com/bf_pwa/index.html?"
    params = "cury=INR&partner={}&rtm={}".format(partner, rtm)
    if user_id and user_id != "undefined":
        params = "userId={}&".format(user_id) + params
    if pwa_uuid:
        params += "&pwa_uuid={}".format(pwa_uuid)
    return base + params + fragment


def make_h5_headers(token=None, partner=None, sourceurl=None):
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://betfugu02.com",
        "referer": "https://betfugu02.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
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
        "isfrom": "other_h5",
        "ispwa": "true",
        "webfonts": "Microsoft YaHei",
        "deviceid": "",
        "visitorid": HAR_VISITOR_ID,
        "sourceurl": sourceurl or "https://betfugu02.com/bf_pwa/index.html#/",
        "webrtc": get_webrtc_ip(),
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
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
}

REDIRECT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def call_api(method, host, path, body=None, token=None, partner=None, game=False, sourceurl=None):
    url = host + path
    if method == "POST":
        data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
    else:
        data = None
    if game or host == GAME_HOST:
        headers = dict(GAME_BASE_HEADERS)
        if token:
            headers["access-token"] = token
    else:
        headers = make_h5_headers(token=token, partner=partner, sourceurl=sourceurl)
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
        return None, None, "", "Partner not found: {}".format(final_url)
    return partner, user_id, rtm, final_url


def generate_random_phone():
    first_digit = random.choice(["6", "7", "8", "9"])
    rest = "".join(random.choice("0123456789") for _ in range(9))
    return first_digit + rest


def step_client_log(pwa_uuid, event):
    body = {"logname": "pwa_log", "event": event, "content": {"pwa_uuid": pwa_uuid}}
    url = H5_HOST + PATH_CLIENT_LOG
    data = json.dumps(body).encode("utf-8")
    headers = {
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://betfugu02.com",
        "referer": "https://betfugu02.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200, "{} logged".format(event)
    except Exception:
        return False, "{} FAIL".format(event)


def step_prelogin_index_v4(partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "indexV4 FAIL"
    return True, "indexV4 OK"


def step_prelogin_dayly_jackpot(partner, sourceurl):
    body = {"id": "daylyJackpot", "version": "1"}
    status, resp = call_api("POST", H5_HOST, PATH_DAYLY_JACKPOT, body=body, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "daylyJackpot FAIL"
    return True, "daylyJackpot OK"


def step_prelogin_game_configs(partner, sourceurl):
    status, resp = call_api("GET", H5_HOST, PATH_GAME_CONFIGS, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "gameConfigs FAIL"
    return True, "gameConfigs OK"


def step_prelogin_item_config(partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_ITEM_CONFIG, body={}, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "itemConfig FAIL"
    return True, "itemConfig OK"


def step_register(phone, encrypted_password, partner, sourceurl):
    body = {"account": phone, "password": encrypted_password, "partner": int(partner), "itemuserfor": VERIFIED_ITEMUSERFOR}
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Register FAIL: {}".format(resp)
    return True, "Registered \u2705"


def step_login(phone, encrypted_password, partner, sourceurl):
    body = {"account": phone, "password": encrypted_password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: {}".format(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login \u2705"


def step_check_regist_gifts(token, partner, sourceurl):
    status, resp = call_api("GET", H5_HOST, PATH_REGIST_GIFTS, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Gift status FAIL"
    return True, "Gift status OK"


def step_homepage_index_v4(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Homepage FAIL"
    return True, "Homepage OK \u2705"


def step_get_free_package(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Free package FAIL"
    return True, "Free package OK \u2705"


def step_claim_gift(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Claim gift FAIL: {}".format(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM for i in items)
    if not found:
        return False, "Gift mismatch: {}".format(items)
    return True, "Gift claimed \u2705 freespinbet10 x10"


def step_get_free_package_after_claim(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "Free package (after) FAIL"
    free_pkg = resp.get("freePackage", {})
    if EXPECTED_GIFT_ID in free_pkg:
        return True, "Free package verified \u2705 {}x".format(free_pkg[EXPECTED_GIFT_ID])
    return True, "Free package: {}".format(free_pkg)


def step_set_language(token, partner, sourceurl):
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Set language FAIL"
    return True, "Language set \u2705"


def step_freespin_subscribe(token):
    body = {"tyid": SUBSCRIBE_TYID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: {}".format(resp)
    return True, "Subscribed \u2705"


def step_play_spins(token):
    """HAR Entries 915-927 - POST /freetinygames/freespin/bet
    FIXED: HAR response format is lotteryGameResult.data.balance/win (NOT data.balance).
    HAR proof Entry 915:
      {"code":200,"lotteryGameResult":{"code":200,"data":{"balance":8,"bet":10,"win":8}},"tycount":9}
    """
    results = []
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body={}, token=token, game=True)
        if status != 200:
            results.append("Spin {}: \u274c HTTP {}".format(i+1, status))
            break
        # HAR verified: data is inside lotteryGameResult.data
        lottery = resp.get("lotteryGameResult", {})
        game_data = lottery.get("data", {})
        balance = game_data.get("balance", "?")
        win = game_data.get("win", 0)
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        results.append("Spin {}/{}: win={} bal={} left={}".format(i+1, NUM_SPINS, win, balance, tycount))
        if tycount == 0 and i < NUM_SPINS - 1:
            break
    return True, "\n".join(results) + "\nTotal win: {}".format(total_win)


def run_full_flow(refer_link):
    report = []
    report.append("\U0001f3b0 BetFugu Auto-Register")
    report.append("Refer link: {}".format(refer_link))
    partner, user_id, rtm, redirect_url = follow_short_link_and_get_partner(refer_link)
    if not partner:
        report.append("\u274c FAIL: {}".format(redirect_url))
        return False, "\n".join(report)
    report.append("Partner: {}".format(partner))
    if user_id:
        report.append("Referrer userId: {}".format(user_id))
    report.append("")

    pwa_uuid = generate_pwa_uuid()
    report.append("pwa_uuid: {}".format(pwa_uuid))
    report.append("webrtc IP: {}".format(get_webrtc_ip()))
    report.append("")

    src_no_uuid = build_sourceurl(user_id, partner, rtm, pwa_uuid=None, fragment="#/")
    src_with_uuid = build_sourceurl(user_id, partner, rtm, pwa_uuid=pwa_uuid, fragment="#/")
    src_with_uuid_login = build_sourceurl(user_id, partner, rtm, pwa_uuid=pwa_uuid, fragment="#/login")

    phone = generate_random_phone()
    report.append("Phone: {}".format(phone))
    report.append("Password: {} (AES)".format(FIXED_PASSWORD))
    report.append("")

    # Pre-register (HAR exact sequence)
    ok, msg = step_client_log(pwa_uuid, "web_open")
    report.append("0\ufe0f\u20e3 web_open: {}".format(msg))
    ok, msg = step_prelogin_dayly_jackpot(partner, src_no_uuid)
    report.append("0\ufe0f\u20e3 daylyJackpot: {}".format(msg))
    ok, msg = step_prelogin_index_v4(partner, src_no_uuid)
    report.append("0\ufe0f\u20e3 indexV4 (no uuid): {}".format(msg))
    ok, msg = step_client_log(pwa_uuid, "pwa_download")
    report.append("0\ufe0f\u20e3 pwa_download: {}".format(msg))
    ok, msg = step_prelogin_index_v4(partner, src_with_uuid)
    report.append("0\ufe0f\u20e3 indexV4 (uuid): {}".format(msg))
    ok, msg = step_prelogin_dayly_jackpot(partner, src_with_uuid)
    report.append("0\ufe0f\u20e3 daylyJackpot(2): {}".format(msg))
    ok, msg = step_prelogin_game_configs(partner, src_with_uuid)
    report.append("0\ufe0f\u20e3 gameConfigs: {}".format(msg))
    ok, msg = step_prelogin_item_config(partner, src_with_uuid_login)
    report.append("0\ufe0f\u20e3 itemConfig: {}".format(msg))
    report.append("")

    try:
        encrypted_password = aes_encrypt(FIXED_PASSWORD)
        report.append("AES encrypt: \u2705".format())
    except Exception as e:
        report.append("AES encrypt: \u274c {}".format(e))
        return False, "\n".join(report)
    report.append("")

    ok, msg = step_register(phone, encrypted_password, partner, src_with_uuid_login)
    report.append("1\ufe0f\u20e3 Register: {}".format(msg))
    if not ok:
        return False, "\n".join(report)
    time.sleep(0.5)

    token, msg = step_login(phone, encrypted_password, partner, src_with_uuid_login)
    report.append("2\ufe0f\u20e3 Login: {}".format(msg))
    if not token:
        return False, "\n".join(report)

    src_post = src_with_uuid
    ok, msg = step_check_regist_gifts(token, partner, src_post)
    report.append("3\ufe0f\u20e3 Gift status: {}".format(msg))
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_get_free_package(token, partner, src_post)
    report.append("4\ufe0f\u20e3 Free package (pre): {}".format(msg))
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_homepage_index_v4(token, partner, src_post)
    report.append("5\ufe0f\u20e3 Homepage: {}".format(msg))
    ok, msg = step_claim_gift(token, partner, src_post)
    report.append("6\ufe0f\u20e3 Claim gift: {}".format(msg))
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_get_free_package_after_claim(token, partner, src_post)
    report.append("7\ufe0f\u20e3 Free package (post): {}".format(msg))
    ok, msg = step_set_language(token, partner, src_post)
    report.append("8\ufe0f\u20e3 Language: {}".format(msg))
    ok, msg = step_freespin_subscribe(token)
    report.append("9\ufe0f\u20e3 Subscribe: {}".format(msg))
    if not ok:
        return False, "\n".join(report)

    report.append("\U0001f51f Playing 10 free spins...")
    ok, spin_report = step_play_spins(token)
    report.append(spin_report)
    report.append("")
    report.append("\u2705 Done! Registration + 10 free spins complete.")
    return True, "\n".join(report)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f3b0 *BetFugu Auto-Register Bot*\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` \u2014 auto register + 10 free spins\n"
        "`/help` \u2014 help\n\n"
        "Example: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "\u26a0\ufe0f Refer link do!\nUse: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
            parse_mode="Markdown",
        )
        return
    refer_link = " ".join(context.args)
    msg = await update.message.reply_text("\U0001f504 Processing... {}".format(refer_link))
    success, report = run_full_flow(refer_link)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "`/register <REFER_LINK>` \u2014 auto register + 10 free spins\n\n"
        "Example: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN not set!")
        raise SystemExit(1)
    print("BetFugu Bot starting...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    print("Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
