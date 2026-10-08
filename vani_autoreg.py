# Vani.ai autoreg — camoufox + Gmail alias + IMAP code + API key harvest.
# Usage: python vani_autoreg.py N   (N accounts, base email from env/const)
# Secrets: gw_key.txt style files; IMAP pass in imap_pass.txt (NOT in repo).
import imaplib, email as emaillib, json, os, re, sys, time, uuid
from datetime import datetime

BASE_EMAIL = os.environ.get("VANI_BASE_EMAIL", "baradok609@gmail.com")
IMAP_USER = os.environ.get("VANI_IMAP_USER", "baradok609@gmail.com")
IMAP_PASS = open(os.path.join(os.path.dirname(__file__), "imap_pass.txt")).read().strip()
OUT = os.path.join(os.path.dirname(__file__), "vani_accounts.jsonl")
SB_COOKIE_NAME = "sb-bfwynudfpppahxozcexw-auth-token"


def alias_email(n):
    base, dom = BASE_EMAIL.split("@")
    return f"{base}+vani{n}@{dom}"


def wait_otp(email_addr, since_ts, timeout=180):
    """Poll Gmail IMAP for vani magic code/link."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com")
            m.login(IMAP_USER, IMAP_PASS)
            m.select("INBOX")
            typ, data = m.search(None, '(SINCE "%s")' % datetime.now().strftime("%d-%b-%Y"))
            ids = data[0].split()
            for mid in reversed(ids[-30:]):
                typ, msgd = m.fetch(mid, "(RFC822)")
                raw = msgd[0][1]
                msg = emaillib.message_from_bytes(raw)
                if "vani" not in (msg.get("From", "") + msg.get("Subject", "")).lower():
                    continue
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="replace")
                m6 = re.search(r"\b(\d{6})\b", body)
                ml = re.search(r"https://c\.vani\.ai/[^\s\"'<>]+token_hash[^\s\"'<>]+", body)
                if not ml:
                    ml = re.search(r"https://c\.vani\.ai/api/auth/[^\s\"'<>]+", body)
                dt = msg.get("Date")
                if m6 or ml:
                    m.logout()
                    return {"code": m6.group(1) if m6 else None,
                            "link": ml.group(0) if ml else None, "date": dt}
            m.logout()
        except Exception as e:
            print("imap err:", str(e)[:80])
        time.sleep(6)
    return None


def register_one(alias, headless=True):
    from camoufox.sync_api import Camoufox
    rec = {"alias": alias, "ts": time.time(), "status": "error"}
    with Camoufox(headless=headless) as browser:
        page = browser.new_page()
        page.goto("https://c.vani.ai/login?next=/chat", timeout=60000)
        page.wait_for_timeout(3000)
        # consent
        for sel in ["button:has-text('Accept')"]:
            try:
                page.click(sel, timeout=2000)
            except Exception:
                pass
        page.fill("input[type=email]", alias)
        since = time.time() - 5
        # wait for invisible turnstile token to be issued (up to 40s)
        tok = ""
        for _ in range(40):
            tok = page.eval_on_selector("input[name=turnstile_token]", "el => el.value") or ""
            if tok:
                break
            page.wait_for_timeout(1000)
        print(f"[{alias}] turnstile token len: {len(tok)}")
        if not tok:
            rec["status"] = "turnstile-blocked"
            return rec
        page.click("button:has-text('Email me a sign-in link')")
        page.wait_for_timeout(5000)
        txt = page.inner_text("body")
        if "security check" in txt.lower():
            # wait for turnstile to solve invisibly then retry
            page.wait_for_timeout(8000)
            try:
                page.click("button:has-text('Email me a sign-in link')", timeout=3000)
                page.wait_for_timeout(4000)
                txt = page.inner_text("body")
            except Exception:
                pass
        if "security check" in txt.lower():
            rec["status"] = "turnstile-blocked"
            return rec
        print(f"[{alias}] email sent, waiting OTP...")
        got = wait_otp(alias, since)
        if not got:
            rec["status"] = "no-email"
            return rec
        if got["link"]:
            page.goto(got["link"], timeout=60000)
            page.wait_for_timeout(6000)
        elif got["code"]:
            # code entry mode: look for code inputs on page
            inputs = page.locator("input[inputmode=numeric], input[maxlength='1']")
            if inputs.count() >= 6:
                for i, ch in enumerate(got["code"]):
                    inputs.nth(i).fill(ch)
                page.wait_for_timeout(5000)
            else:
                single = page.locator("input[type=text], input[name=code]")
                if single.count():
                    single.first.fill(got["code"])
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(5000)
                else:
                    rec["status"] = "no-code-input"
                    return rec
        # extract auth cookie
        cookies = page.context.cookies("https://c.vani.ai")
        auth = next((c for c in cookies if c["name"] == SB_COOKIE_NAME), None)
        if not auth:
            rec["status"] = "no-auth-cookie"
            rec["url"] = page.url
            return rec
        rec["status"] = "registered"
        rec["cookie"] = auth["value"]
        # create API key
        page.goto("https://c.vani.ai/settings/developer", timeout=60000)
        page.wait_for_timeout(4000)
        try:
            page.click("button:has-text('Create key')", timeout=5000)
            page.wait_for_timeout(1500)
            dlg = page.locator("[role=dialog]").first
            dlg.locator("input").first.fill(f"farm-{uuid.uuid4().hex[:6]}")
            try:
                dlg.locator("text=No expiry").first.click(timeout=2000)
            except Exception:
                pass
            page.wait_for_timeout(500)
            dlg.locator("button:has-text('Create key')").click()
            page.wait_for_timeout(4000)
            body = page.inner_text("body")
            mk = re.search(r"vani_[a-f0-9]{40,80}", body)
            if mk:
                rec["api_key"] = mk.group(0)
        except Exception as e:
            rec["key_err"] = str(e)[:100]
        # usage snapshot
        try:
            page.goto("https://c.vani.ai/chat", timeout=60000)
            page.wait_for_timeout(3000)
        except Exception:
            pass
    return rec


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    start = int(sys.argv[2]) if len(sys.argv) > 2 else int(time.time()) % 10000
    ok = 0
    for i in range(n):
        alias = alias_email(start + i)
        print(f"=== {i+1}/{n} {alias} ===")
        try:
            rec = register_one(alias)
        except Exception as e:
            rec = {"alias": alias, "status": "exception", "err": str(e)[:200]}
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        has_key = bool(rec.get("api_key"))
        print(f"-> {rec['status']} key={'YES' if has_key else 'NO'}")
        if rec["status"] == "registered":
            ok += 1
        time.sleep(3)
    print(f"DONE ok={ok}/{n}")


if __name__ == "__main__":
    main()
