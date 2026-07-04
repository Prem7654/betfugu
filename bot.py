#!/usr/bin/env python3
"""
BetFugu Bot - Telegram bot for free spins.
/register <link>  - auto register + 10 spins (old flow)
/spin <phone> <password>  - login with your account + play 10 free spins
"""
import os, json, random, time, uuid, base64, threading
import urllib.request, urllib.error
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

_AES_KEY = b"34d80508ab4a03043f014a66840ba23w"
_AES_IV = b"585280b3543d2d89"
H5 = "https://h5server.betfuguapi.com"
GAME = "https://game.betfuguapi.com"
VISITOR = "MB==d9f771e6f02f464acd2a8ae95601599ff40dfc88202627"

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
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "language":"en-US","appid":"wecardgame","channel":"test","currency":"INR",
        "version":"2.11.56","timezone":"Asia/Calcutta","timeoffset":"-330","network":"4g",
        "publisher":"release","platform":"Unknown","basepkgname":"h5","pkgname":"h5","osv":"10",
        "weblang":"en-US","weblangs":"en-US,en,en-IN","isfrom":"other_h5","ispwa":"true",
        "webfonts":"Microsoft YaHei","deviceid":"","visitorid":VISITOR,
        "sourceurl":sourceurl or "https://betfugu02.com/bf_pwa/index.html#/",
        "webrtc":"47.31.86.36","trackertoken":"","trackername":""}
    if partner: h["partner"] = str(partner)
    if token: h["access-token"] = token
    return h

def mk_game_headers(token):
    h = {"accept":"*/*","content-type":"application/json",
        "origin":"https://www.betfugu02.com","referer":"https://www.betfugu02.com/",
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"}
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

def run_spins(phone, password):
    r = []
    r.append("BetFugu Free Spins")
    r.append("Phone: " + phone)
    r.append("")
    try:
        enc = aes_encrypt(password)
        r.append("AES encrypt: OK")
    except Exception as e:
        r.append("AES FAIL: " + str(e))
        return False, "\n".join(r)
    rtm = str(int(time.time() * 1000))
    pwa = gen_pwa()
    src_login = build_src("", 66666666, rtm, pwa, "#/login")
    src_uuid = build_src("", 66666666, rtm, pwa, "#/")
    r.append("")
    r.append("--- Login ---")
    body = {"account": phone, "password": enc}
    st, resp = call_api("POST", H5, "/user/login/account", body, None, 66666666, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r.append("Login FAIL: " + json.dumps(resp)[:300])
        return False, "\n".join(r)
    token = resp.get("token")
    if not token:
        r.append("Login FAIL: no token")
        r.append("Response: " + json.dumps(resp)[:300])
        return False, "\n".join(r)
    r.append("Login: OK (token received)")
    user_info = resp.get("data", resp)
    uid = user_info.get("id", user_info.get("userId", "?"))
    balance = user_info.get("balance", user_info.get("money", "?"))
    r.append("User ID: " + str(uid))
    r.append("Balance: " + str(balance))
    time.sleep(1)
    r.append("")
    r.append("--- Subscribe to free spins ---")
    st, resp = call_api("POST", GAME, "/freetinygames/freespin/subscribe", {"typeid": "freespinbet10"}, token, None, True, "")
    if st == 200:
        r.append("Subscribe: OK")
        r.append("  Resp: " + json.dumps(resp)[:200])
    else:
        r.append("Subscribe: FAIL (may already be subscribed)")
        r.append("  Resp: " + json.dumps(resp)[:200])
    time.sleep(1)
    r.append("")
    r.append("--- Playing 10 free spins ---")
    total_win = 0
    for i in range(10):
        st, resp = call_api("POST", GAME, "/freetinygames/freespin/bet", {}, token, None, True, "")
        if st != 200:
            r.append("Spin " + str(i+1) + ": FAIL HTTP " + str(st))
            r.append("  Resp: " + json.dumps(resp)[:200])
            break
        lottery = resp.get("lotteryGameResult", {})
        gd = lottery.get("data", {})
        win = gd.get("win", 0)
        bal = gd.get("balance", "?")
        bet = gd.get("bet", 10)
        tycount = resp.get("tycount", "?")
        total_win += win if isinstance(win, (int, float)) else 0
        r.append("Spin " + str(i+1) + "/10: win=" + str(win) + " bal=" + str(bal) + " left=" + str(tycount))
        if tycount == 0 and i < 9:
            r.append("No spins left!")
            break
        time.sleep(1)
    r.append("")
    r.append("Total win: " + str(total_win))
    r.append("Done!")
    return True, "\n".join(r)

def run_register(refer_link):
    r = ["BetFugu Auto-Register", "Refer: " + refer_link]
    partner = "66666666"
    uid = ""
    rtm = str(int(time.time() * 1000))
    r.append("Partner: " + partner)
    pwa = gen_pwa()
    phone = random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))
    r.append("Phone: " + phone)
    src_login = build_src(uid, partner, rtm, pwa, "#/login")
    src_uuid = build_src(uid, partner, rtm, pwa, "#/")
    src_no_uuid = build_src(uid, partner, rtm, None, "#/")
    try: enc = aes_encrypt("123456")
    except Exception as e: r.append("AES FAIL: " + str(e)); return False, "\n".join(r)
    r.append("")
    r.append("--- Pre-login ---")
    call_api("POST", H5, "/shorturl", {"text": "https://betfugu02.com/app/index.html?userId=undefined&cury=INR&partner=undefined&rtm=" + rtm}, None, partner, False, "https://betfugu02.com/bf_pwa/index.html#/")
    r.append("shorturl: OK")
    call_api("POST", H5, "/opendata/homepage/indexV4", {}, None, partner, False, src_no_uuid)
    r.append("indexV4: OK")
    call_api("POST", H5, "/opendata/getdaylyjackpot", {"id": "daylyJackpot", "version": "1"}, None, partner, False, src_no_uuid)
    r.append("daylyJackpot: OK")
    call_api("POST", H5, "/opendata/homepage/indexV4", {}, None, partner, False, src_uuid)
    r.append("indexV4(uuid): OK")
    call_api("GET", H5, "/opendata/gameConfigs", None, None, partner, False, src_uuid)
    r.append("gameConfigs: OK")
    call_api("POST", H5, "/opendata/itemConfig", {}, None, partner, False, src_login)
    r.append("itemConfig: OK")
    time.sleep(2)
    r.append("")
    r.append("--- Register ---")
    body = {"account": phone, "password": enc, "partner": int(partner), "itemuserfor": "freespin"}
    st, resp = call_api("POST", H5, "/user/register/account", body, None, partner, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r.append("Register FAIL: " + json.dumps(resp)[:300])
        return False, "\n".join(r)
    r.append("Register: OK")
    time.sleep(1)
    st, resp = call_api("POST", H5, "/user/login/account", {"account": phone, "password": enc}, None, partner, False, src_login)
    if st != 200 or resp.get("code") != 200:
        r.append("Login FAIL: " + json.dumps(resp)[:300])
        return False, "\n".join(r)
    token = resp.get("token")
    if not token: r.append("Login FAIL: no token"); return False, "\n".join(r)
    r.append("Login: OK")
    r.append("")
    r.append("--- Post-register ---")
    st, resp = call_api("POST", H5, "/user/profile/getfreepackage", {}, token, partner, False, src_uuid)
    r.append("FreePkg: " + ("OK" if st==200 else "FAIL") + " " + json.dumps(resp)[:150])
    st, resp = call_api("POST", H5, "/user/profile/claimRegisterGifts", {}, token, partner, False, src_uuid)
    r.append("Claim: " + ("OK" if st==200 else "FAIL") + " " + json.dumps(resp)[:150])
    call_api("POST", H5, "/user/profile/setlanguage", {"language": "en-US"}, token, partner, False, src_uuid)
    r.append("Lang: OK")
    st, resp = call_api("POST", GAME, "/freetinygames/freespin/subscribe", {"typeid": "freespinbet10"}, token, None, True, "")
    r.append("Subscribe: " + ("OK" if st==200 else "FAIL"))
    r.append("")
    r.append("--- 10 spins ---")
    tw = 0
    for i in range(10):
        st, resp = call_api("POST", GAME, "/freetinygames/freespin/bet", {}, token, None, True, "")
        if st != 200: r.append("Spin " + str(i+1) + ": FAIL"); break
        lot = resp.get("lotteryGameResult", {}); gd = lot.get("data", {})
        w = gd.get("win", 0); b = gd.get("balance", "?"); tc = resp.get("tycount", "?")
        tw += w if isinstance(w, (int, float)) else 0
        r.append("Spin " + str(i+1) + "/10: win=" + str(w) + " bal=" + str(b) + " left=" + str(tc))
        if tc == 0 and i < 9: break
        time.sleep(1)
    r.append("")
    r.append("Total win: " + str(tw))
    r.append("Phone: " + phone + " | Password: 123456")
    return True, "\n".join(r)

async def cmd_start(update, context):
    await update.message.reply_text(
        "BetFugu Bot\n\n"
        "/spin <phone> <password> - login + 10 free spins\n"
        "Example: /spin 9469551049 123456\n\n"
        "/register <link> - auto register + 10 spins\n"
        "Example: /register https://s.betfugu01.com/ezzwvl51eipuy39"
    )

async def cmd_spin(update, context):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /spin <phone> <password>\nExample: /spin 9469551049 123456")
        return
    phone = context.args[0]
    password = context.args[1]
    msg = await update.message.reply_text("Processing spins for " + phone + "...")
    success, report = run_spins(phone, password)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)

async def cmd_register(update, context):
    if not context.args:
        await update.message.reply_text("Refer link do! /register <link>")
        return
    refer_link = " ".join(context.args)
    msg = await update.message.reply_text("Processing...")
    success, report = run_register(refer_link)
    for i in range(0, len(report), 4000):
        chunk = report[i:i+4000]
        if i == 0:
            await msg.edit_text(chunk)
        else:
            await update.message.reply_text(chunk)

async def cmd_help(update, context):
    await update.message.reply_text(
        "/spin <phone> <password> - login + 10 free spins\n"
        "/register <link> - auto register + 10 spins"
    )

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("No BOT_TOKEN!")
        return
    print("BetFugu Bot starting...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("spin", cmd_spin))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    app.run_polling()

if __name__ == "__main__":
    main()