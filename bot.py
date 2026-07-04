#!/usr/bin/env python3
"""
BetFugu Auto-Register Bot - Telegram + HTTP WebApp server.
Serves index.html on port 8080 (Railway) so browser uses phone IP.
Telegram bot runs in background thread.
"""

import os
import re
import json
import random
import time
import uuid
import base64
import socket
import threading
import http.server
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlparse, parse_qs

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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
    node_js = "const crypto=require('crypto');const k=Buffer.from(process.argv[1],'utf8');const v=Buffer.from(process.argv[2],'utf8');const c=crypto.createCipheriv('aes-256-cbc',k,v);let e=c.update(process.argv[3],'utf8');e=Buffer.concat([e,c.final()]);process.stdout.write(e.toString('base64'));"
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
        "language": "en-US", "appid": "wecardgame", "channel": "test", "currency": "INR",
        "version": "2.11.56", "timezone": "Asia/Calcutta", "timeoffset": "-330",
        "network": "4g", "publisher": "release", "platform": "Unknown", "basepkgname": "h5",
        "pkgname": "h5", "osv": "10", "weblang": "en-US", "weblangs": "en-US,en,en-IN",
        "isfrom": "other_h5", "ispwa": "true", "webfonts": "Microsoft YaHei", "deviceid": "",
        "visitorid": HAR_VISITOR_ID,
        "sourceurl": sourceurl or "https://betfugu02.com/bf_pwa/index.html#/",
        "webrtc": get_webrtc_ip(), "trackertoken": "", "trackername": "",
    }
    if partner:
        headers["partner"] = str(partner)
    if token:
        headers["access-token"] = token
    return headers


GAME_BASE_HEADERS = {
    "accept": "*/*", "content-type": "application/json",
    "origin": "https://www.betfugu02.com", "referer": "https://www.betfugu02.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
}

SHORTURL_HEADERS = {
    "accept": "*/*", "content-type": "application/json",
    "origin": "https://betfugu02.com", "referer": "https://betfugu02.com/",
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
    req = urllib.request.Request(short_url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
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


def run_full_flow(refer_link):
    report = []
    report.append(" BetFugu Auto-Register")
    report.append("Refer: " + refer_link)
    partner, user_id, rtm, redirect_url = follow_short_link_and_get_partner(refer_link)
    if not partner:
        report.append("FAIL: " + redirect_url)
        return False, "\n".join(report)
    report.append("Partner: " + str(partner))
    if user_id:
        report.append("Referrer: " + str(user_id))
    report.append("")
    pwa_uuid = generate_pwa_uuid()
    phone = generate_random_phone()
    report.append("Phone: " + phone)
    report.append("Pwd: 123456 (AES)")
    report.append("")
    src_login = build_sourceurl(user_id, partner, rtm, pwa_uuid, "#/login")
    src_uuid = build_sourceurl(user_id, partner, rtm, pwa_uuid, "#/")
    src_no_uuid = build_sourceurl(user_id, partner, rtm, None, "#/")
    ok, msg = step_shorturl()
    report.append("shorturl: " + msg)
    status, resp = call_api("POST", H5_HOST, PATH_INDEX_V4, body={}, partner=partner, sourceurl=src_no_uuid)
    report.append("indexV4: " + ("OK" if status == 200 else "FAIL"))
    time.sleep(3)
    try:
        encrypted_password = aes_encrypt(FIXED_PASSWORD)
    except Exception as e:
        report.append("AES FAIL: " + str(e))
        return False, "\n".join(report)
    report.append("AES: OK")
    body = {"account": phone, "password": encrypted_password, "partner": int(partner), "itemuserfor": VERIFIED_ITEMUSERFOR}
    status, resp = call_api("POST", H5_HOST, PATH_REGISTER, body=body, partner=partner, sourceurl=src_login)
    if status != 200 or resp.get("code") != 200:
        report.append("Register FAIL: " + str(resp))
        return False, "\n".join(report)
    report.append("Register: OK")
    time.sleep(1)
    body = {"account": phone, "password": encrypted_password}
    status, resp = call_api("POST", H5_HOST, PATH_LOGIN, body=body, partner=partner, sourceurl=src_login)
    if status != 200 or resp.get("code") != 200:
        report.append("Login FAIL: " + str(resp))
        return False, "\n".join(report)
    token = resp.get("token")
    if not token:
        report.append("Login FAIL: no token")
        return False, "\n".join(report)
    report.append("Login: OK")
    status, resp = call_api("POST", H5_HOST, PATH_GET_FREEPACKAGE, body={}, token=token, partner=partner, sourceurl=src_uuid)
    report.append("FreePkg: " + ("OK" if status == 200 else "FAIL"))
    status, resp = call_api("POST", H5_HOST, PATH_CLAIM_GIFT, body={}, token=token, partner=partner, sourceurl=src_uuid)
    report.append("Claim: " + ("OK" if status == 200 else "FAIL"))
    body = {"language": SET_LANGUAGE}
    status, resp = call_api("POST", H5_HOST, PATH_SET_LANGUAGE, body=body, token=token, partner=partner, sourceurl=src_uuid)
    report.append("Lang: " + ("OK" if status == 200 else "FAIL"))
    body = {"typeid": SUBSCRIBE_TYPEID}
    status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_SUBSCRIBE, body=body, token=token, game=True)
    report.append("Subscribe: " + ("OK" if status == 200 else "FAIL"))
    report.append("Spins:")
    total_win = 0
    for i in range(NUM_SPINS):
        status, resp = call_api("POST", GAME_HOST, PATH_FREESPIN_BET, body={}, token=token, game=True)
        if status != 200:
            report.append("  Spin " + str(i+1) + ": FAIL")
            break
        lottery = resp.get("lotteryGameResult", {})
        gd = lottery.get("data", {})
        win = gd.get("win", 0)
        bal = gd.get("balance", "?")
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        report.append("  Spin " + str(i+1) + "/10: win=" + str(win) + " bal=" + str(bal) + " left=" + str(tycount))
        if tycount == 0 and i < NUM_SPINS - 1:
            break
        time.sleep(1)
    report.append("Total win: " + str(total_win))
    report.append("Done! Phone: " + phone)
    return True, "\n".join(report)


async def cmd_start(update, context):
    await update.message.reply_text(
        "BetFugu Auto-Register Bot\n\n"
        "/register <REFER_LINK> - auto register + 10 free spins\n"
        "Example: /register https://s.betfugu01.com/ezzwvl51eipuy39",
    )


async def cmd_register(update, context):
    if not context.args:
        await update.message.reply_text("Refer link do! /register <link>")
        return
    refer_link = " ".join(context.args)
    msg = await update.message.reply_text("Processing...")
    success, report = run_full_flow(refer_link)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)


async def cmd_help(update, context):
    await update.message.reply_text("/register <REFER_LINK> - auto register + 10 free spins")


def run_telegram_bot():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("No BOT_TOKEN, skipping telegram bot")
        return
    print("Telegram bot starting...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    app.run_polling()


def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.exists(html_path):
        html_path = "/app/index.html"
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                try:
                    with open(html_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(content.encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(("Error: " + str(e)).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, format, *args):
            pass
    print("HTTP server starting on port " + str(port))
    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


def main():
    _setup_proxy()
    print("BetFugu Bot starting...")
    if _PROXY_URL:
        print("Using proxy: " + _PROXY_URL)
    if _PROXY_IP:
        print("Using webrtc IP: " + _PROXY_IP)
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    print("Telegram bot started in background")
    run_http_server()


if __name__ == "__main__":
    main()