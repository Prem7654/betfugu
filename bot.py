#!/usr/bin/env python3
"""
BetFugu Auto-Register + Free Spin Bot - Telegram + HAR-verified.
No guessing. Every endpoint, header, body from original HAR file (1037 entries).
KEY FIXES: see comments inline.
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
from urllib.parse import import urlencode, urlparse, parse_qs

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

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
    node_js = "const crypto=require(\"crypto\");const k=Buffer.from(process.argv[1],\"utf8\");const v=Buffer.from(process.argv[2],\"utf8\");const c=crypto.createCipheriv(\"aes-256-cbc\",k,v);let e=c.update(process.argv[3],\"utf8\");e=Buffer.concat([e,c.final()]);process.stdout.write(e.toString("base64"));"
    result = subprocess.run(["node", "-e", node_js, key.decode("utf-8"), iv.decode("utf-8"), plaintext], capture_output=True, text=True, timeout=10)
    if result.returncode == 0 and result.stdout:
        return result.stdout.strip()
    raise RuntimeError("AES encryption failed")


H5_HOST = "https://h5server.betfuguapi.com"
GAME_HOST = "https://game.betfuguapi.com"

PATH_REGISTER = "/user/register/account"
PATH_LOGIN = "/user/login/account"
PATH_REGISTER_GIFTS = "/opendata/homepage/registerGifts"
PATH_INDEX_V4 = "/opendata/homepage/indexV4"
PATH_GET_FREEPACKAGE = "/user/profile/getfreepackage"
PATH_CLAIM_GIFT = "/user/profile/claimRegisterGifts"
PATH_SET_LANGUAGE = "/user/profile/setlanguage"
PATH_GAME_CONFIGS = "/opendata/gameConfigs"
PATH_DAYLY_JACKPOT = "/opendata/getdaylyjackpot"
PATH_ITEM_CONFIG = "/opendata/itemConfig"
PATH_CLIENT_LOG = "/client/log"
PATH_SHORTURL = "/shorturl"
PATH_FREESPIN_SUBSCRIBE = "/freetinygames/freespin/subscribe"
PATH_FREESPIN_BET = "/freetinygames/freespin/bet"

VERIFIED_ITEMUSERFOR = "freespin"
EXPECTED_GIFT_ID = "freespinbet10"
EXPECTED_GIFT_NUM = 10
SUBSCRIBE_TYPEID = "freespinbet10"
NUM_SPINS = 10
FIXED_PASSWORD = "123456"
SET_LANGUAGE = "en-US"
HAR_VISITOR_ID = "MB==d9f771e6f02f464acd2a8ae95601599ff40dfc88202627"

_PROXY_URL = os.environ.get("PROXY_URL", "")
_PROXY_IP = os.environ.get("PROXY_IP", "")


def _setup_proxy():
    if not _PROXY_URL:
        return
    proxy_handler = urllib.request.ProxyHandler({"http": _PROXY_URL, "https": _PROXY_URL})
    opener = urllib.request.build_opener(proxy_handler)
    urllib.request.install_opener(opener)
    print("Proxy configured: " + _PROXY_URL)


_server_ip = None

def get_webrtc_ip():
    global _server_ip
    if _PROXY_IP:
        return _PROXY_IP
    if _server_ip is None:
        try:
            req = urllib.request.Request("https://api.ipify.org?format=text", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                _server_ip = resp.read().decode("utf-8").strip()
        except Exception:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                _server_ip = s.getsockname()[0]
                s.close()
            except Exception:
                _server_ip = ""
        print("Server IP: " + _server_ip)
    return _server_ip


def generate_pwa_uuid():
    return uuid.uuid4().hex


def build_sourceurl(user_id, partner, rtm, pwa_uuid=None, fragment="#/"):
    base = "https://betfugu02.com/bf_pwa/index.html?"
    params = "cury=INR&partner=" + str(partner) + "&rtm=" + str(rtm)
    if user_id and user_id != "undefined":
        params = "userId=" + str(user_id) + "&" + params
    if pwa_uuid:
        params += "&pwa_uuid=" + pwa_uuid
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
        "timeoffset": "-330",
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

SHORTURL_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://betfugu02.com",
    "referer": "https://betfugu02.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
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
        return None, None, "", "Partner not found: " + final_url
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
            return resp.status == 200, event + " logged"
    except Exception:
        return False, event + " FAIL"


def step_shorturl():
    rtm = str(int(time.time() * 1000))
    body = {"text": "https://betfugu02.com/app/index.html?userId=undefined&cury=INR&partner=undefined&rtm=" + rtm}
    url = H5_HOST + PATH_SHORTURL
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=SHORTURL_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, "shorturl OK"
    except Exception as e:
        return False, "shorturl FAIL: " + str(e)


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
        return False, "Register FAIL: " + str(resp)
    return True, "Registered ✅"


def step_login(phone, encrypted_password, partner, sourceurl):
    body = {"account": phone, "password": encrypted_password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return None, "Login FAIL: " + str(resp)
    token = resp.get("token")
    if not token:
        return None, "Login FAIL: no token"
    return token, "Login ✅"


def step_check_register_gifts(token, partner, sourceurl):
    status, resp = call_api("GET", H5_HOST, PATH_REGISTER_GIFTS, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Gift status FAIL"
    return True, "Gift status OK"


def step_homepage_index_v4(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Homepage FAIL"
    return True, "Homepage OK ✅"


def step_get_free_package(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Free package FAIL"
    return True, "Free package OK ✅"


def step_claim_gift(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Claim gift FAIL: " + str(resp)
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM for i in items)
    if not found:
        return False, "Gift mismatch: " + str(items)
    return True, "Gift claimed ✅ freespinbet10 x10"


def step_get_free_package_after_claim(token, partner, sourceurl):
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200:
        return False, "Free package (after) FAIL"
    free_pkg = resp.get("freePackage", {})
    if EXPECTED_GIFT_ID in free_pkg:
        return True, "Free package verified ✅ " + str(free_pkg[EXPECTED_GIFT_ID]) + "x"
    return True, "Free package: " + str(free_pkg)


def step_set_language(token, partner, sourceurl):
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner, sourceurl=sourceurl)
    if status != 200 or resp.get("code") != 200:
        return False, "Set language FAIL"
    return True, "Language set ✅"


def step_freespin_subscribe(token):
    body = {"typeid": SUBSCRIBE_TYPEID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    if status != 200 or resp.get("code") != 200:
        return False, "Subscribe FAIL: " + str(resp)
    return True, "Subscribed ✅"


def step_play_spins(token):
    results = []
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body={}, token=token, game=True)
        if status != 200:
            results.append("Spin " + str(i+1) + ": FAIL HTTP " + str(status))
            break
        lottery = resp.get("lotteryGameResult", {})
        game_data = lottery.get("data", {})
        balance = game_data.get("balance", "?")
        win = game_data.get("win", 0)
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        results.append("Spin " + str(i+1) + "/" + str(NUM_SPINS) + ": win=" + str(win) + " bal=" + str(balance) + " left=" + str(tycount))
        if tycount == 0 and i < NUM_SPINS - 1:
            break
        time.sleep(1)
    return True, "\n".join(results) + "\nTotal win: " + str(total_win)


def run_full_flow(refer_link):
    report = []
    report.append("🎰 BetFugu Auto-Register")
    report.append("Refer link: " + refer_link)
    partner, user_id, rtm, redirect_url = follow_short_link_and_get_partner(refer_link)
    if not partner:
        report.append("FAIL: " + redirect_url)
        return False, "\n".join(report)
    report.append("Partner: " + str(partner))
    if user_id:
        report.append("Referrer userId: " + str(user_id))
    report.append("")

    pwa_uuid = generate_pwa_uuid()
    report.append("pwa_uuid: " + pwa_uuid)
    webrtc_ip = get_webrtc_ip()
    report.append("webrtc IP: " + webrtc_ip)
    if _PROXY_URL:
        report.append("Proxy: " + _PROXY_URL)
    report.append("")

    src_no_uuid = build_sourceurl(user_id, partner, rtm, pwa_uuid=None, fragment="#/")
    src_with_uuid = build_sourceurl(user_id, partner, rtm, pwa_uuid=pwa_uuid, fragment="#/")
    src_with_uuid_login = build_sourceurl(user_id, partner, rtm, pwa_uuid=pwa_uuid, fragment="#/login")

    phone = generate_random_phone()
    report.append("Phone: " + phone)
    report.append("Password: " + FIXED_PASSWORD + " (AES)")
    report.append("")

    ok, msg = step_client_log(pwa_uuid, "web_open")
    report.append("0️⃣ web_open: " + msg)
    time.sleep(3)

    ok, msg = step_shorturl()
    report.append("0️⃣ shorturl(1): " + msg)

    ok, msg = step_prelogin_dayly_jackpot(partner, src_no_uuid)
    report.append("0️⃣ daylyJackpot: " + msg)

    ok, msg = step_prelogin_index_v4(partner, src_no_uuid)
    report.append("1️⃣ indexV4 (no uuid): " + msg)
    time.sleep(1)

    ok, msg = step_client_log(pwa_uuid, "pwa_download")
    report.append("0️⃣ pwa_download: " + msg)

    ok, msg = step_shorturl()
    report.append("0️⃣ shorturl(2): " + msg)

    ok, msg = step_prelogin_index_v4(partner, src_with_uuid)
    report.append("0️⃣ indexV4 (uuid): " + msg)

    ok, msg = step_prelogin_dayly_jackpot(partner, src_with_uuid)
    report.append("0️⃣ daylyJackpot(2): " + msg)

    ok, msg = step_prelogin_game_configs(partner, src_with_uuid)
    report.append("0️⃣ gameConfigs: " + msg)
    time.sleep(1)

    ok, msg = step_prelogin_item_config(partner, src_with_uuid_login)
    report.append("0️⃣ itemConfig: " + msg)
    report.append("")

    time.sleep(5)

    try:
        encrypted_password = aes_encrypt(FIXED_PASSWORD)
        report.append("AES encrypt: ✅")
    except Exception as e:
        report.append("AES encrypt: FAIL " + str(e))
        return False, "\n".join(report)
    report.append("")

    ok, msg = step_register(phone, encrypted_password, partner, src_with_uuid_login)
    report.append("1️⃣ Register: " + msg)
    if not ok:
        return False, "\n".join(report)
    time.sleep(1)

    token, msg = step_login(phone, encrypted_password, partner, src_with_uuid_login)
    report.append("2️⃣ Login: " + msg)
    if not token:
        return False, "\n".join(report)

    src_post = src_with_uuid
    ok, msg = step_check_register_gifts(token, partner, src_post)
    report.append("3️⃣ Gift status: " + msg)
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_get_free_package(token, partner, src_post)
    report.append("4️⃣ Free package (pre): " + msg)
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_homepage_index_v4(token, partner, src_post)
    report.append("5️⃣ Homepage: " + msg)
    ok, msg = step_claim_gift(token, partner, src_post)
    report.append("6️⃣ Claim gift: " + msg)
    if not ok:
        return False, "\n".join(report)
    ok, msg = step_get_free_package_after_claim(token, partner, src_post)
    report.append("7️⃣ Free package (post): " + msg)
    ok, msg = step_set_language(token, partner, src_post)
    report.append("8️⃣ Language: " + msg)
    ok, msg = step_freespin_subscribe(token)
    report.append("9️⃣ Subscribe: " + msg)
    if not ok:
        return False, "\n".join(report)

    report.append("🎰 Playing 10 free spins...")
    ok, spin_report = step_play_spins(token)
    report.append(spin_report)
    report.append("")
    report.append("✅ Done! Registration + 10 free spins complete.")
    return True, "\n".join(report)


async def cmd_start(update, context):
    proxy_info = "\nProxy: " + _PROXY_URL if _PROXY_URL else "\nNo proxy set"
    await update.message.reply_text(
        "🎰 *BetFugu Auto-Register Bot*\n\n"
        "Commands:\n"
        "`/register <REFER_LINK>` - auto register + 10 free spins\n"
        "`/help` - help\n\n"
        "Example: `/register https://s.betfugu01.com/ezzwvl51eipuy39`"
        + proxy_info,
        parse_mode="Markdown",
    )


async def cmd_register(update, context):
    if not context.args:
        await update.message.reply_text(
            "Refer link do!\nUse: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
            parse_mode="Markdown",
        )
        return
    refer_link = " ".join(context.args)
    msg = await update.message.reply_text("Processing... " + refer_link)
    success, report = run_full_flow(refer_link)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)


async def cmd_help(update, context):
    await update.message.reply_text(
        "`/register <REFER_LINK>` - auto register + 10 free spins\n\n"
        "Example: `/register https://s.betfugu01.com/ezzwvl51eipuy39`",
        parse_mode="Markdown",
    )


def main():
    _setup_proxy()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN not set!")
        raise SystemExit(1)
    print("BetFugu Bot starting...")
    if _PROXY_URL:
        print("Using proxy: " + _PROXY_URL)
    if _PROXY_IP:
        print("Using webrtc IP: " + _PROXY_IP)
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    print("Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()