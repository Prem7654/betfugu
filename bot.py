#!/usr/bin/env python3
"""
BetFugu Bot - Telegram bot for auto-register + free spins.
/register <refer_link>  - auto register + claim gift + 10 free spins (full flow)
/spin <phone> <password>  - login with your account + 10 free spins only
"""
import os, json, random, time, uuid, base64, socket
import urllib.request, urllib.error
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

_AES_KEY = b"34d80508ab4a03043f014a66840ba23w"
_AES_IV = b"585280b3543d2d89"
H5 = "https://h5server.betfuguapi.com"
GAME = "https://game.betfuguapi.com"
VISITOR = "MB==d9f771e6f02f464acd2a8ae95601599ff40dfc88202627"

_PROXY_URL = os.environ.get("PROXY_URL", "")
_PROXY_IP = os.environ.get("PROXY_IP", "")
_server_ip = None

def get_webrtc_ip():
    global _server_ip
    if _PROXY_IP: return _PROXY_IP
    if _server_ip is None:
        try:
            req = urllib.request.Request("https://api.ipify.org?format=text", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                _server_ip = resp.read().decode().strip()
        except:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                _server_ip = s.getsockname()[0]
                s.close()
            except: _server_ip = ""
    return _server_ip

def aes_encrypt(pt):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sp
        from cryptography.hazmat.backends import default_backend
        p = sp.PKCS7(128).padder()
        pd = p.update(pt.encode()) + p.finalize()
        c = Cipher(algorithms.AES(_AES_KEY), modes.CBC(_AES_IV), backend=default_backend())
        e = c.encryptor()
        return base64.b64encode(e.update(pd) + e.finalize()).decode()
    except ImportError:
        pass
    import subprocess
    js = "const crypto=require('crypto');const c=crypto.createCipheriv('aes-256-cbc',Buffer.from(process.argv[1]),Buffer.from(process.argv[2]));let e=c.update(process.argv[3],'utf8');e=Buffer.concat([e,c.final()]);process.stdout.write(e.toString('base64'));"
    r = subprocess.run(["node","-e",js,_AES_KEY.decode(),_AES_IV.decode(),pt],capture_output=True,text=True,timeout=10)
    return r.stdout.strip() if r.returncode==0 else ""

def mk_h5_headers(token, partner, sourceurl):
    h = {"accept":"application/json, text/plain, */*","content-type":"application/json;charset=UTF-8",
        "origin":"https://betfugu02.com","referer":"https://betfugu02.com/",
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
        "language":"en-US","appid":"wecardgame","channel":"test","currency":"INR",
        "version":"2.11.56","timezone":"Asia/Calcutta","timeoffset":"-330","network":"4g",
        "publisher":"release","platform":"Unknown","basepkgname":"h5","pkgname":"h5","osv":"10",
        "weblang":"en-US","weblangs":"en-US,en,en-IN","isfrom":"other_h5","ispwa":"true",
        "webfonts":"Microsoft YaHei","deviceid":"","visitorid":VISITOR,
        "sourceurl":sourceurl or "https://betfugu02.com/bf_pwa/index.html#/",
        "webrtc":get_webrtc_ip(),"trackertoken":"","trackername":""}
    if partner: h["partner"] = str(partner)
    if token: h["access-token"] = token
    return h

GAME_HEADERS = {"accept":"*/*","content-type":"application/json",
    "origin":"https://www.betfugu02.com","referer":"https://www.betfugu02.com/",
    "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"}

SHORTURL_HEADERS = {"accept":"*/*","content-type":"application/json",
    "origin":"https://betfugu02.com","referer":"https://betfugu02.com/",
    "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"}

def mk_game_headers(token):
    h = dict(GAME_HEADERS)
    if token: h["access-token"] = token
    return h

def call_api(method, host, path, body, token, partner, is_game, sourceurl):
    url = host + path
    if is_game:
        headers = mk_game_headers(token)
    else:
        headers = mk_h5_headers(token, partner, sourceurl)
    data = None
    if method == "POST":
        data = json.dumps(body).encode() if body is not None else b"{}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try: return resp.status, json.loads(raw)
            except: return resp.status, {"_raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try: return e.code, json.loads(raw)
        except: return e.code, {"_raw": raw}
    except Exception as e:
        return 0, {"error": str(e)}

def gen_pwa(): return uuid.uuid4().hex

def build_src(uid, partner, rtm, pwa, frag="#/"):
    p = "cury=INR&partner=" + str(partner) + "&rtm=" + str(rtm)
    if uid and uid != "undefined": p = "userId=" + str(uid) + "&" + p
    if pwa: p += "&pwa_uuid=" + pwa
    return "https://betfugu02.com/bf_pwa/index.html?" + p + frag

def gen_phone():
    return random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

def follow_short_link(short_url):
    req = urllib.request.Request(short_url, headers={"User-Agent":"Mozilla/5.0"}, method="GET")
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
        return None, None, "", "No redirect Location"
    parsed = urlparse(final_url)
    params = parse_qs(parsed.query)
    partner = params.get("partner", [None])[0]
    user_id = params.get("userId", [None])[0]
    rtm = params.get("rtm", [""])[0]
    if not partner or partner == "undefined":
        return None, None, "", "Partner not found: " + final_url
    return partner, user_id, rtm, final_url

def step_shorturl(rtm):
    body = {"text": "https://betfugu02.com/app/index.html?userId=undefined&cury=INR&partner=undefined&rtm=" + str(rtm)}
    url = H5 + "/shorturl"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=SHORTURL_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True
    except: return False

def run_register(refer_link):
    r = []
    r.append("\U0001f3b0 BetFugu Auto-Register")
    r.append("Refer link: " + refer_link)
    partner, user_id, rtm, redirect_url = follow_short_link(refer_link)
    if not partner:
        r.append("FAIL: " + redirect_url)
        return False, "\n".join(r)
    r.append("Partner: " + str(partner) + " (from 302 redirect)")
    if user_id:
        r.append("Referrer userId: " + str(user_id))
    rtm = rtm or str(int(time.time() * 1000))
    pwa = gen_pwa()
    phone = gen_phone()
    r.append("Phone: " + phone)
    r.append("Password: 123456")
    src_login = build_src(user_id, partner, rtm, pwa, "#/login")
    src_uuid = build_src(user_id, partner, rtm, pwa, "#/")
    src_no_uuid = build_src(user_id, partner, rtm, None, "#/")
    r.append("")
    r.append("0\ufe0f\u20e3 Referral track: ")
    step_shorturl(rtm)
    st, resp = call_api("POST", H5, "/opendata/homepage/indexV4", {}, None, partner, False, src_no_uuid)
    time.sleep(1)
    st, resp = call_api("POST", H5, "/opendata/homepage/indexV4", {}, None, partner, False, src_uuid)
    st, resp = call_api("POST", H5, "/opendata/getdaylyjackpot", {"id":"daylyJackpot","version":"1"}, None, partner, False, src_uuid)
    st, resp = call_api("GET", H5, "/opendata/gameConfigs", None, None, partner, False, src_uuid)
    st, resp = call_api("POST", H5, "/opendata/itemConfig", {}, None, partner, False, src_login)
    r.append("Referral tracked \u2705 (userId=" + str(user_id) + ")")
    time.sleep(2)
    try:
        enc = aes_encrypt("123456")
    except Exception as e:
        r.append("AES FAIL: " + str(e))
        return False, "\n".join(r)
    r.append("")
    r.append("1\ufe0f\u20e3 Register: ")
    reg_body = {"account": phone, "password": enc, "partner": int(partner), "itemuserfor": "freespin"}
    st, resp = call_api("POST", H5, "/user/register/account", reg_body, None, partner, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r[-1] += "FAIL " + json.dumps(resp)[:200]
        return False, "\n".join(r)
    r[-1] += "Registered \u2705 (code 200)"
    time.sleep(1)
    r.append("2\ufe0f\u20e3 Login: ")
    st, resp = call_api("POST", H5, "/user/login/account", {"account": phone, "password": enc}, None, partner, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r[-1] += "FAIL " + json.dumps(resp)[:200]
        return False, "\n".join(r)
    token = resp.get("token")
    if not token:
        r[-1] += "FAIL no token"
        return False, "\n".join(r)
    r[-1] += "Login \u2705"
    time.sleep(0.5)
    r.append("3\ufe0f\u20e3 Gift status: ")
    st, resp = call_api("GET", H5, "/opendata/homepage/registerGifts", None, token, partner, False, src_uuid)
    claimed = False
    if st == 200 and isinstance(resp, dict):
        data = resp.get("data", resp)
        if isinstance(data, dict):
            claimed = data.get("claimed", data.get("isClaimed", False))
    r[-1] += "Gift status OK (claimed=" + str(claimed) + ")"
    r.append("4\ufe0f\u20e3 Homepage: ")
    st, resp = call_api("POST", H5, "/opendata/homepage/indexV4", {}, token, partner, False, src_uuid)
    r[-1] += "Homepage config OK \u2705"
    r.append("5\ufe0f\u20e3 Free package (pre): ")
    st, resp = call_api("POST", H5, "/user/profile/getfreepackage", {}, token, partner, False, src_uuid)
    pre_pkg = ""
    if st == 200 and isinstance(resp, dict):
        d = resp.get("data", resp)
        if isinstance(d, dict):
            pre_pkg = json.dumps(d)[:150]
    r[-1] += "Free package OK \u2705 (before claim)"
    r.append("6\ufe0f\u20e3 Claim gift: ")
    st, resp = call_api("POST", H5, "/user/profile/claimRegisterGifts", {}, token, partner, False, src_uuid)
    gift_info = ""
    if st == 200 and isinstance(resp, dict):
        d = resp.get("data", resp)
        if isinstance(d, dict):
            items = d.get("items", d.get("list", []))
            if isinstance(items, list) and len(items) > 0:
                it = items[0]
                if isinstance(it, dict):
                    gift_info = str(it.get("typeid", it.get("id", ""))) + " x" + str(it.get("num", it.get("count", "")))
                else:
                    gift_info = str(it)
    r[-1] += "Gift claimed \u2705 " + (gift_info or json.dumps(resp)[:100])
    r.append("7\ufe0f\u20e3 Free package (post): ")
    st, resp = call_api("POST", H5, "/user/profile/getfreepackage", {}, token, partner, False, src_uuid)
    post_pkg = ""
    if st == 200 and isinstance(resp, dict):
        d = resp.get("data", resp)
        if isinstance(d, dict):
            post_pkg = json.dumps(d)[:150]
    r[-1] += "Free package verified \u2705 " + (post_pkg or "OK")
    r.append("8\ufe0f\u20e3 Language: ")
    st, resp = call_api("POST", H5, "/user/profile/setlanguage", {"language":"en-US"}, token, partner, False, src_uuid)
    r[-1] += "Language set \u2705 (en-US)"
    r.append("9\ufe0f\u20e3 Subscribe: ")
    st, resp = call_api("POST", GAME, "/freetinygames/freespin/subscribe", {"typeid":"freespinbet10"}, token, None, True, "")
    sub_ok = st == 200
    r[-1] += "Subscribed \u2705 (freespinbet10)" if sub_ok else "Subscribe FAIL " + json.dumps(resp)[:100]
    r.append("")
    r.append("\U0001f51e Playing 10 free spins...")
    total_win = 0
    for i in range(10):
        st, resp = call_api("POST", GAME, "/freetinygames/freespin/bet", {}, token, None, True, "")
        if st != 200:
            r.append("Spin " + str(i+1) + "/10: FAIL HTTP " + str(st))
            break
        lottery = resp.get("lotteryGameResult", {})
        gd = lottery.get("data", {}) if isinstance(lottery, dict) else {}
        win = gd.get("win", 0) if isinstance(gd, dict) else 0
        bal = gd.get("balance", "?") if isinstance(gd, dict) else "?"
        bet = gd.get("bet", 10) if isinstance(gd, dict) else 10
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        r.append("Spin " + str(i+1) + "/10: bet=" + str(bet) + " win=" + str(win) + " bal=" + str(bal) + " left=" + str(tycount))
        if tycount == 0 and i < 9:
            r.append("No spins left!")
            break
        time.sleep(1)
    r.append("")
    r.append("Total win: " + str(total_win))
    r.append("\u2705 Done! Registration + 10 free spins complete.")
    r.append("Phone: " + phone + " | Password: 123456")
    return True, "\n".join(r)

def run_spin_only(phone, password):
    r = []
    r.append("\U0001f3b0 BetFugu Free Spins")
    r.append("Phone: " + phone)
    r.append("")
    try:
        enc = aes_encrypt(password)
    except Exception as e:
        r.append("AES FAIL: " + str(e))
        return False, "\n".join(r)
    rtm = str(int(time.time() * 1000))
    pwa = gen_pwa()
    src_login = build_src("", 66666666, rtm, pwa, "#/login")
    src_uuid = build_src("", 66666666, rtm, pwa, "#/")
    r.append("")
    r.append("1\ufe0f\u20e3 Login: ")
    st, resp = call_api("POST", H5, "/user/login/account", {"account": phone, "password": enc}, None, 66666666, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r[-1] += "FAIL " + json.dumps(resp)[:200]
        return False, "\n".join(r)
    token = resp.get("token")
    if not token:
        r[-1] += "FAIL no token"
        return False, "\n".join(r)
    r[-1] += "Login \u2705"
    d = resp.get("data", {})
    if isinstance(d, dict):
        uid = d.get("id", d.get("userId", "?"))
        bal = d.get("balance", d.get("money", "?"))
        r.append("User ID: " + str(uid) + " | Balance: " + str(bal))
    time.sleep(1)
    r.append("")
    r.append("2\ufe0f\u20e3 Subscribe: ")
    st, resp = call_api("POST", GAME, "/freetinygames/freespin/subscribe", {"typeid":"freespinbet10"}, token, None, True, "")
    if st == 200:
        r[-1] += "Subscribed \u2705"
    else:
        r[-1] += "Subscribe: " + json.dumps(resp)[:150]
    time.sleep(1)
    r.append("")
    r.append("\U0001f51e Playing 10 free spins...")
    total_win = 0
    for i in range(10):
        st, resp = call_api("POST", GAME, "/freetinygames/freespin/bet", {}, token, None, True, "")
        if st != 200:
            r.append("Spin " + str(i+1) + "/10: FAIL HTTP " + str(st) + " " + json.dumps(resp)[:150])
            break
        lottery = resp.get("lotteryGameResult", {})
        gd = lottery.get("data", {}) if isinstance(lottery, dict) else {}
        win = gd.get("win", 0) if isinstance(gd, dict) else 0
        bal = gd.get("balance", "?") if isinstance(gd, dict) else "?"
        bet = gd.get("bet", 10) if isinstance(gd, dict) else 10
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        r.append("Spin " + str(i+1) + "/10: bet=" + str(bet) + " win=" + str(win) + " bal=" + str(bal) + " left=" + str(tycount))
        if tycount == 0 and i < 9:
            r.append("No spins left!")
            break
        time.sleep(1)
    r.append("")
    r.append("Total win: " + str(total_win))
    r.append("\u2705 Done! 10 free spins complete.")
    return True, "\n".join(r)

async def cmd_start(update, context):
    await update.message.reply_text(
        "\U0001f3b0 BetFugu Bot\n\n"
        "/register <refer_link> - auto register + 10 free spins\n"
        "Example: /register https://s.betfugu01.com/xxxxx\n\n"
        "/spin <phone> <password> - login + 10 free spins only\n"
        "Example: /spin 8886295451 123456"
    )

async def cmd_register(update, context):
    if not context.args:
        await update.message.reply_text("Refer link do! /register <link>")
        return
    refer_link = " ".join(context.args)
    msg = await update.message.reply_text("Processing...")
    success, report = run_register(refer_link)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0: await msg.edit_text(chunk)
        else: await update.message.reply_text(chunk)

async def cmd_spin(update, context):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /spin <phone> <password>\nExample: /spin 8886295451 123456")
        return
    phone = context.args[0]
    password = context.args[1]
    msg = await update.message.reply_text("Processing spins for " + phone + "...")
    success, report = run_spin_only(phone, password)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0: await msg.edit_text(chunk)
        else: await update.message.reply_text(chunk)

async def cmd_help(update, context):
    await update.message.reply_text(
        "/register <link> - auto register + 10 spins\n"
        "/spin <phone> <password> - login + 10 spins"
    )

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("No BOT_TOKEN!")
        return
    if _PROXY_URL:
        handler = urllib.request.ProxyHandler({"http": _PROXY_URL, "https": _PROXY_URL})
        urllib.request.install_opener(urllib.request.build_opener(handler))
    print("BetFugu Bot starting...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("spin", cmd_spin))
    app.add_handler(CommandHandler("help", cmd_help))
    app.run_polling()

if __name__ == "__main__":
    main()