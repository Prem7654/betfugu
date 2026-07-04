#!/usr/bin/env python3
"""
BetFugu Auto-Register Bot - Telegram + HTTP WebApp with CORS proxy.
Serves index.html + /api/* proxy endpoints to bypass CORS.
Telegram bot in background thread.
"""
import os, json, random, time, uuid, base64, socket, threading
import http.server, urllib.request, urllib.error
from urllib.parse import urlparse, parse_qs
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

def mk_h5_headers(extra):
    h = {"accept":"application/json, text/plain, */*","content-type":"application/json;charset=UTF-8",
        "origin":"https://betfugu02.com","referer":"https://betfugu02.com/",
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "language":"en-US","appid":"wecardgame","channel":"test","currency":"INR",
        "version":"2.11.56","timezone":"Asia/Calcutta","timeoffset":"-330","network":"4g",
        "publisher":"release","platform":"Unknown","basepkgname":"h5","pkgname":"h5","osv":"10",
        "weblang":"en-US","weblangs":"en-US,en,en-IN","isfrom":"other_h5","ispwa":"true",
        "webfonts":"Microsoft YaHei","deviceid":"","visitorid":VISITOR,
        "sourceurl":extra.get("sourceurl","https://betfugu02.com/bf_pwa/index.html#/"),
        "webrtc":extra.get("webrtc",""),"trackertoken":"","trackername":""}
    if extra.get("partner"): h["partner"] = str(extra["partner"])
    if extra.get("access-token"): h["access-token"] = extra["access-token"]
    return h

def mk_game_headers(token):
    h = {"accept":"*/*","content-type":"application/json","origin":"https://www.betfugu02.com",
        "referer":"https://www.betfugu02.com/","user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if token: h["access-token"] = token
    return h

def do_call(host, path, method, body, extra, token, is_game):
    url = host + path
    headers = mk_game_headers(token) if is_game else mk_h5_headers(extra or {})
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

def run_flow(refer_link):
    r = ["BetFugu Auto-Register","Refer: "+refer_link]
    partner = "66666666"; uid = ""; rtm = str(int(time.time()*1000))
    r.append("Partner: "+partner)
    pwa = uuid.uuid4().hex
    phone = random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))
    r.append("Phone: "+phone)
    src_login = f"https://betfugu02.com/bf_pwa/index.html?userId={uid}&cury=INR&partner={partner}&rtm={rtm}&pwa_uuid={pwa}#/login"
    src_uuid = f"https://betfugu02.com/bf_pwa/index.html?userId={uid}&cury=INR&partner={partner}&rtm={rtm}&pwa_uuid={pwa}#/"
    try: enc = aes_encrypt("123456")
    except Exception as e: r.append("AES FAIL: "+str(e)); return False, "\n".join(r)
    extra = {"partner":partner,"sourceurl":src_login,"webrtc":""}
    st, resp = do_call(H5,"/user/register/account","POST",{"account":phone,"password":enc,"partner":int(partner),"itemuserfor":"freespin"},extra,None,False)
    if st != 200 or resp.get("code") != 200: r.append("Register FAIL: "+str(resp)); return False, "\n".join(r)
    r.append("Register: OK")
    time.sleep(1)
    st, resp = do_call(H5,"/user/login/account","POST",{"account":phone,"password":enc},extra,None,False)
    if st != 200 or resp.get("code") != 200: r.append("Login FAIL: "+str(resp)); return False, "\n".join(r)
    token = resp.get("token")
    if not token: r.append("Login FAIL: no token"); return False, "\n".join(r)
    r.append("Login: OK")
    ex2 = {"partner":partner,"sourceurl":src_uuid,"webrtc":"","access-token":token}
    st,_ = do_call(H5,"/user/profile/getfreepackage","POST",{},ex2,token,False)
    r.append("FreePkg: "+("OK" if st==200 else "FAIL"))
    st,rc = do_call(H5,"/user/profile/claimRegisterGifts","POST",{},ex2,token,False)
    r.append("Claim: "+("OK" if st==200 else "FAIL")+" "+json.dumps(rc)[:200])
    st,_ = do_call(H5,"/user/profile/setlanguage","POST",{"language":"en-US"},ex2,token,False)
    r.append("Lang: "+("OK" if st==200 else "FAIL"))
    st,_ = do_call(GAME,"/freetinygames/freespin/subscribe","POST",{"typeid":"freespinbet10"},{},token,True)
    r.append("Subscribe: "+("OK" if st==200 else "FAIL"))
    tw = 0
    for i in range(10):
        st,resp = do_call(GAME,"/freetinygames/freespin/bet","POST",{},{},token,True)
        if st != 200: r.append(f"Spin {i+1}: FAIL"); break
        lot = resp.get("lotteryGameResult",{}); gd = lot.get("data",{})
        w = gd.get("win",0); b = gd.get("balance","?"); tc = resp.get("tycount","?")
        tw += w if isinstance(w,(int,float)) else 0
        r.append(f"Spin {i+1}/10: win={w} bal={b} left={tc}")
        if tc == 0 and i < 9: break
        time.sleep(1)
    r.append("Total win: "+str(tw)); r.append("Done! Phone: "+phone)
    return True, "\n".join(r)

async def cmd_start(update, context):
    await update.message.reply_text("BetFugu Bot\n/register <link> - auto register + 10 spins")
async def cmd_register(update, context):
    if not context.args: await update.message.reply_text("Refer link do!"); return
    msg = await update.message.reply_text("Processing...")
    _, report = run_flow(" ".join(context.args))
    await msg.edit_text(report[:4000])
async def cmd_help(update, context):
    await update.message.reply_text("/register <link>")

def run_tg():
    tk = os.environ.get("BOT_TOKEN")
    if not tk: print("No BOT_TOKEN"); return
    print("Telegram starting...")
    app = ApplicationBuilder().token(tk).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("help", cmd_help))
    app.run_polling()

def run_http():
    port = int(os.environ.get("PORT", 8080))
    hp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.exists(hp): hp = "/app/index.html"
    class H(http.server.BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def do_GET(self):
            if self.path in ("/","/index.html"):
                try:
                    with open(hp, encoding="utf-8") as f: c = f.read()
                    self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self._cors(); self.end_headers()
                    self.wfile.write(c.encode())
                except Exception as e:
                    self.send_response(500); self._cors(); self.end_headers()
                    self.wfile.write(str(e).encode())
            elif self.path.startswith("/api/"):
                self._api("GET")
            else:
                self.send_response(404); self._cors(); self.end_headers()
        def do_POST(self):
            if self.path.startswith("/api/"): self._api("POST")
            else: self.send_response(404); self._cors(); self.end_headers()
        def _api(self, method):
            try:
                cl = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(cl) if cl > 0 else b"{}"
                body = json.loads(raw.decode()) if raw else {}
            except: body = {}
            host = body.get("host",""); path = body.get("path","")
            is_game = body.get("isGame", False); token = body.get("token","")
            extra = body.get("headers",{}); ab = body.get("body",{})
            if not host or not path:
                self.send_response(400); self._cors(); self.end_headers()
                self.wfile.write(b'{"error":"missing host/path"}'); return
            st, resp = do_call(host, path, method, ab, extra, token, is_game)
            out = json.dumps({"status": st, "data": resp}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json"); self._cors(); self.end_headers()
            self.wfile.write(out)
        def log_message(self, *a): pass
    print(f"HTTP server on port {port}")
    http.server.HTTPServer(("0.0.0.0", port), H).serve_forever()

def main():
    print("BetFugu Bot starting...")
    t = threading.Thread(target=run_tg, daemon=True); t.start()
    run_http()

if __name__ == "__main__": main()