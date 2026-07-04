#!/usr/bin/env python3
"""
BetFugu registration-only bot.

IMPORTANT: This bot is built strictly from verified HAR evidence.
No guessing. Every endpoint, field name, and value comes from the HAR
report (betfugu_har_full_report.md) that you uploaded.

Verified endpoints (from the HAR report):
  1. Domain redirect    : GET  https://h5server.betfuguapi.com/opendata/domainRedirect
  2. Registration       : POST https://h5server.betfuguapi.com/user/register/account
  3. Login              : POST https://h5server.betfuguapi.com/user/login/account
  4. Claim registration gift: POST https://h5server.betfuguapi.com/user/profile/claimRegistGifts

Verified request fields (sanitized in the report):
  - Registration body fields: account, password, partner, itemuserfor
  - Partner code           : 66666666
  - itemuserfor            : "freespin"
  - Login body fields      : account, password
  - Login returns          : {"code":200, "token": "..."}
  - Claim gift returns     : {"code":200, "items":[{"id":"freespinbet10","num":10}]}

Usage:
  python3 betfugu_reg_bot.py --phone 9xxxxxxxxxx --password YourPass123

The bot will:
  1) GET domainRedirect
  2) POST register/account
  3) POST login/account
  4) POST claimRegistGifts

Each step is printed with proof (HTTP status + response code).
No payment, no spin, no deposit — registration only.
"""

import argparse, json, sys

import urllib.request
import urllib.error

# ---- Verified constants (from the HAR report) ----
BASE_HOST = "https://h5server.betfuguapi.com"
PATH_DOMAIN_REDIRECT = "/opendata/domainRedirect"
PATH_REGISTER = "/user/register/account"
PATH_LOGIN = "/user/login/account"
PATH_CLAIM_GIFT = "/user/profile/claimRegistGifts"

VERIFIED_PARTNER = 66666666       # Entry 271 request body
VERIFIED_ITEMUSERFOR = "freespin" # Entry 271 request body
EXPECTED_GIFT_ID = "freespinbet10" # Entry 288 response body
EXPECTED_GIFT_NUM = 10              # Entry 288 response body

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


def call_api(method, host, path, body=None, token=None, extra_params=None):
    """Make a single API call, return (http_status, response_json)."""
    url = host + path
    if extra_params:
        from urllib.parse import urlencode
        url += "?" + urlencode(extra_params)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = dict(COMMON_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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


def step_domain_redirect():
    """Verified: Entry 96 — GET /opendata/domainRedirect?domain=betfugu02.com.
    Response: {"code":200,"data":{"domain":"betfugu02.com","country":"IN","currency":"INR"}}
    """
    print("\n[Step 1/4] Domain redirect")
    print("  Endpoint : {}{}".format(BASE_HOST, PATH_DOMAIN_REDIRECT))
    print("  Evidence : HAR Entry 96, status 200")
    status, body = call_api("GET", BASE_HOST, PATH_DOMAIN_REDIRECT, extra_params={"domain": "betfugu02.com"})
    print("  HTTP {}".format(status))
    print("  Response : {}".format(json.dumps(body, ensure_ascii=False)))
    code = body.get("code")
    if status != 200 or code != 200:
        return _fail("Domain redirect expected HTTP 200 + code 200")
    data = body.get("data") or {}
    if data.get("domain") != "betfugu02.com":
        return _fail("Unexpected domain in redirect response")
    print_ok("Domain verified -> betfugu02.com (IN / INR)")
    return True


def step_register(phone, password):
    """Verified: Entry 271 — POST /user/register/account.
    Request body (sanitized): {account, password, partner:66666666, itemuserfor:"freespin"}
    Response: {"code":200}
    """
    print("\n[Step 2/4] Registration")
    print("  Endpoint : {}{}".format(BASE_HOST, PATH_REGISTER))
    print("  Evidence : HAR Entry 271, status 200, response {\"code\":200}")
    body = {
        "account": phone,
        "password": password,
        "partner": VERIFIED_PARTNER,
        "itemuserfor": VERIFIED_ITEMUSERFOR,
    }
    print("  Partner   : {}  (verified from HAR)".format(VERIFIED_PARTNER))
    print("  itemuserfor: {}  (verified from HAR)".format(VERIFIED_ITEMUSERFOR))
    status, resp = call_api("POST", BASE_HOST, PATH_REGISTER, body=body)
    print("  HTTP {}".format(status))
    print("  Response : {}".format(json.dumps(resp, ensure_ascii=False)))
    if status != 200:
        return _fail("Registration HTTP failed")
    if resp.get("code") != 200:
        return _fail("Registration response code is not 200")
    print_ok("Account registered (server returned code 200)")
    return True


def step_login(phone, password):
    """Verified: Entry 274 — POST /user/login/account.
    Request body: {account, password}
    Response: {"code":200, "token": "..."}
    """
    print("\n[Step 3/4] Login")
    print("  Endpoint : {}{}".format(BASE_HOST, PATH_LOGIN))
    print("  Evidence : HAR Entry 274, status 200, returns {\"code\":200,\"token\":\"...\"}")
    body = {"account": phone, "password": password}
    status, resp = call_api("POST", BASE_HOST, PATH_LOGIN, body=body)
    print("  HTTP {}".format(status))
    token = resp.get("token")
    if token:
        # Don't print full token — same as sanitizer in the report.
        print("  Token    : {}...{}".format(token[:6], token[-3:]))
    else:
        print("  Response : {}".format(json.dumps(resp, ensure_ascii=False)))
    if status != 200 or resp.get("code") != 200:
        return _fail("Login failed")
    if not token:
        return _fail("Login did not return a token")
    print_ok("Login success — auth token received (redacted)")
    return token


def step_claim_gift(token):
    """Verified: Entry 288 — POST /user/profile/claimRegistGifts.
    Response: {"code":200,"items":[{"id":"freespinbet10","num":10}]}
    """
    print("\n[Step 4/4] Claim registration gift")
    print("  Endpoint : {}{}".format(BASE_HOST, PATH_CLAIM_GIFT))
    print("  Evidence : HAR Entry 288, status 200, items=[freespinbet10 x10]")
    status, resp = call_api("POST", BASE_HOST, PATH_CLAIM_GIFT, body={}, token=token)
    print("  HTTP {}".format(status))
    print("  Response : {}".format(json.dumps(resp, ensure_ascii=False)))
    if status != 200 or resp.get("code") != 200:
        return _fail("Claim gift failed")
    items = resp.get("items") or []
    found = any(i.get("id") == EXPECTED_GIFT_ID and i.get("num") == EXPECTED_GIFT_NUM for i in items)
    if not found:
        return _fail("Expected gift item freespinbet10 x10 not present")
    print_ok("Gift claimed: freespinbet10 x10 (verified match)")
    return True


def _fail(msg):
    print("  [FAIL] " + msg)
    return False


def print_ok(msg):
    print("  [OK] " + msg)


def main():
    p = argparse.ArgumentParser(
        description="BetFugu registration-only bot (no guessing, HAR-verified)"
    )
    p.add_argument("--phone", required=True, help="Account / phone number to register")
    p.add_argument("--password", required=True, help="Password for the account")
    args = p.parse_args()

    print("=" * 64)
    print("BetFugu Registration Bot — HAR-verified, registration only")
    print("=" * 64)
    print("Phone        : {}".format(args.phone))
    print("Partner code : {}  (verified: HAR Entry 271)".format(VERIFIED_PARTNER))
    print("itemuserfor    : {}  (verified: HAR Entry 271)".format(VERIFIED_ITEMUSERFOR))
    print("Expected gift : {} x{}  (verified: HAR Entry 288)".format(EXPECTED_GIFT_ID, EXPECTED_GIFT_NUM))

    # Step 1 — domain redirect (verified)
    if not step_domain_redirect():
        sys.exit(1)

    # Step 2 — registration (verified)
    if not step_register(args.phone, args.password):
        sys.exit(1)

    # Step 3 — login (verified)
    token = step_login(args.phone, args.password)
    if not token:
        sys.exit(1)

    # Step 4 — claim registration gift (verified)
    if not step_claim_gift(token):
        sys.exit(1)

    print("\n" + "=" * 64)
    print("Registration flow complete. Nothing else was attempted.")
    print("No deposit, no spins, no payment — registration + gift claim only.")
    print("=" * 64)


if __name__ == "__main__":
    main()
