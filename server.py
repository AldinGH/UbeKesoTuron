import datetime
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import shutil
import smtplib
import socketserver
import threading
import time
import traceback
import urllib.parse
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.environ.get("UBEKESO_DATA") or os.path.join(HERE, "data.json")
BACKUP_DIR = os.path.join(os.path.dirname(DATA_FILE), "backups")
BACKUP_KEEP = 14


MAIL_FILE = os.path.join(HERE, "mail_settings.json")


def mail_settings():
    user = os.environ.get("UBEKESO_SMTP_USER")
    password = os.environ.get("UBEKESO_SMTP_PASSWORD")
    if not (user and password) and os.path.exists(MAIL_FILE):
        try:
            with open(MAIL_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            user = user or cfg.get("gmail_address")
            password = password or cfg.get("app_password")
        except (OSError, ValueError):
            pass
    user = (user or "").strip()
    password = re.sub(r"\s+", "", password or "")
    if user and password and "@" in user and not user.startswith("your.") and password != "xxxxxxxxxxxxxxxx":
        return user, password
    return None


def mail_ready():
    return mail_settings() is not None


def show_demo_code():
    return (not mail_ready()) and os.environ.get("UBEKESO_DEMO_CODES", "1") != "0"


def send_mail(to, subject, body):
    settings = mail_settings()
    if settings is None:
        print("[email not set up] To: {}  Subject: {}\n{}".format(to, subject, body))
        return False
    user, password = settings
    msg = EmailMessage()
    msg["From"] = "UbeKeso Cart <{}>".format(user)
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print("[email failed] {}: {}".format(type(exc).__name__, exc))
        return False


ADMIN_EMAIL = (os.environ.get("UBEKESO_ADMIN_EMAIL") or "admin@ubekeso.ph").strip().lower()
ADMIN_PASSWORD = os.environ.get("UBEKESO_ADMIN_PASSWORD") or "Admin#2026"
ADMIN_PASSWORD_IS_DEFAULT = not os.environ.get("UBEKESO_ADMIN_PASSWORD")


CONFIG = {
    "price": 25,
    "extra_cheese_price": 5,
    "cost_per_piece": 10,
    "daily_target": 40,
    "month_goal": 26000,
    "stamps_for_free": 10,
    "low_at": 10,
    "running_low_at": 20,
    "stock_bar_max": 60,
    "min_password": 8,
}


MEDIA_DIR = os.path.join(HERE, "media")
MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
}
PROMO_NAMES = ("promo.mp4", "promo.webm", "promo.mov")
MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")

SESSION_DAYS = 30
ONLINE_SECS = 15
RESET_MINUTES = 10
MAX_PIECES = 60
ACTIVE_STATUSES = ("new", "frying", "ready")
PESO = "\u20b1"

LOCK = threading.RLock()
DB = {}
VERSION = [int(time.time())]
SEEN = {}
RESET_CODES = {}
RESET_REQUESTS = {}
ORDER_REQUESTS = {}
FAILS = {}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def now():
    return time.time()


def today_str():
    return datetime.date.today().isoformat()


def peso(n):
    return "{}{:,}".format(PESO, int(n))


def norm_phone(text):
    d = re.sub(r"[\s\-().]", "", str(text or ""))
    if d.startswith("+"):
        d = d[1:]
    if not d or not all(c in "0123456789" for c in d):
        return None
    if d.startswith("63") and len(d) == 12:
        d = "0" + d[2:]
    elif len(d) == 10 and d.startswith("9"):
        d = "0" + d
    if len(d) == 11 and d.startswith("09"):
        return d
    return None


GMAIL_DOMAINS = ("gmail.com", "googlemail.com")


def canonical_email(e):
    local, _, domain = e.rpartition("@")
    if domain in GMAIL_DOMAINS:
        return local.split("+")[0].replace(".", "") + "@gmail.com"
    return e


def check_gmail(text):
    e = str(text or "").strip().lower()
    local, _, domain = e.rpartition("@")
    if domain not in GMAIL_DOMAINS or not local:
        return None, "Please use a Gmail address that ends with @gmail.com."
    base = local.split("+")[0]
    if (".." in base or base.startswith(".") or base.endswith(".")
            or not re.fullmatch(r"[a-z0-9.]+", base) or not 6 <= len(base.replace(".", "")) <= 30):
        return None, "That is not a valid Gmail address. Check it for typos."
    return canonical_email(e), None


def parse_identifier(text):
    s = str(text or "").strip()
    if "@" in s:
        e = s.lower()
        return ("email", canonical_email(e)) if EMAIL_RE.match(e) and len(e) <= 120 else (None, None)
    p = norm_phone(s)
    return ("phone", p) if p else (None, None)


def clean_name(value):
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    return s if 2 <= len(s) <= 60 else None


def clean_address(value):
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    return s if 5 <= len(s) <= 200 else None


def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex(), digest.hex()


_DUMMY_SALT, _DUMMY_HASH = hash_pw("dummy-password")


def check_pw(user, password):
    if user is None:
        hash_pw(password, bytes.fromhex(_DUMMY_SALT))
        return False
    _, digest = hash_pw(password, bytes.fromhex(user["salt"]))
    return hmac.compare_digest(digest, user["hash"])


def password_problem(pw):
    if not isinstance(pw, str) or len(pw) < CONFIG["min_password"]:
        return "Password needs at least {} characters.".format(CONFIG["min_password"])
    if len(pw) > 128:
        return "Password is too long."
    return None


def fresh_db():
    return {
        "users": {},
        "sessions": {},
        "orders": [],
        "next_order_id": 1,
        "cards": [],
        "stock": [
            {"name": "Cheese", "left": 0},
            {"name": "Lumpia wrappers", "left": 0},
            {"name": "Malagkit rice", "left": 0},
            {"name": "Ube condensed milk", "left": 0},
        ],
        "day": today_str(),
        "sold_today": 0,
        "extra_rev": 0,
        "history": {},
        "activity": [],
    }


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def backup_files():
    try:
        return sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("data-") and f.endswith(".json"))
    except OSError:
        return []


def make_backup():
    if not os.path.exists(DATA_FILE):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        target = os.path.join(BACKUP_DIR, "data-{}.json".format(today_str()))
        shutil.copyfile(DATA_FILE, target)
        for old in backup_files()[:-BACKUP_KEEP]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except OSError as exc:
        print("Backup skipped:", exc)


def load():
    global DB
    DB = fresh_db()
    loaded = False
    if os.path.exists(DATA_FILE):
        try:
            DB.update(read_json(DATA_FILE))
            loaded = True
        except (OSError, ValueError):
            os.replace(DATA_FILE, DATA_FILE + ".bad")
            print("data.json could not be read. It was renamed to data.json.bad.")
            DB = fresh_db()
            for name in reversed(backup_files()):
                try:
                    DB.update(read_json(os.path.join(BACKUP_DIR, name)))
                    print("Restored your data from backups/{}.".format(name))
                    loaded = True
                    break
                except (OSError, ValueError):
                    DB = fresh_db()
    if loaded:
        make_backup()
    for entry in DB["activity"]:
        if not entry.get("id"):
            entry["id"] = secrets.token_hex(4)
    created = False
    if not any(u["role"] == "admin" for u in DB["users"].values()):
        kind, value = parse_identifier(ADMIN_EMAIL)
        if kind != "email":
            value = "admin@ubekeso.ph"
        new_user("Owner", "admin", "email", value, ADMIN_PASSWORD, must_change=ADMIN_PASSWORD_IS_DEFAULT)
        created = True
    save()
    return created


def save():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(DB, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)
    try:
        fd = os.open(os.path.dirname(DATA_FILE) or ".", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def bump():
    VERSION[0] += 1
    save()


def new_user(name, role, kind, value, password, must_change=False, created_by=None):
    uid = "u" + secrets.token_hex(4)
    salt, digest = hash_pw(password)
    user = {
        "id": uid, "name": name, "role": role,
        "email": value if kind == "email" else None,
        "phone": value if kind == "phone" else None,
        "salt": salt, "hash": digest, "active": True, "must_change": must_change,
        "created": now(), "created_by": created_by, "last_login": None, "card_id": None,
    }
    DB["users"][uid] = user
    return user


def find_user(kind, value):
    for u in DB["users"].values():
        if u.get(kind) == value:
            return u
    return None


def log(user, text):
    DB["activity"].append({
        "id": secrets.token_hex(4),
        "ts": now(),
        "actor_id": user["id"] if user else None,
        "actor": user["name"] if user else "System",
        "role": user["role"] if user else "system",
        "text": text,
    })
    if len(DB["activity"]) > 500:
        del DB["activity"][:-500]


def card_by_id(card_id):
    for c in DB["cards"]:
        if c["id"] == card_id:
            return c
    return None


def create_card(name, phone=None):
    nums = []
    for c in DB["cards"]:
        try:
            nums.append(int(c["id"].split("-")[1]))
        except (IndexError, ValueError):
            pass
    card = {"id": "UK-{:03d}".format(max(nums + [0]) + 1), "name": name, "stamps": 0,
            "sample": False, "phone": phone}
    DB["cards"].append(card)
    return card


def card_for_phone(phone, name):
    for c in DB["cards"]:
        if c.get("phone") == phone:
            return c
    return create_card(name, phone)


def add_stamp(card):
    if card and card["stamps"] < CONFIG["stamps_for_free"]:
        card["stamps"] += 1
        return True
    return False


def deduct_stock(pieces):
    for item in DB["stock"]:
        item["left"] = max(0, item["left"] - pieces)


def order_total(pieces, extra):
    return pieces * (CONFIG["price"] + (CONFIG["extra_cheese_price"] if extra else 0))


def roll_day():
    today = today_str()
    if DB["day"] != today:
        DB["history"][DB["day"]] = DB["sold_today"]
        DB["day"] = today
        DB["sold_today"] = 0
        DB["extra_rev"] = 0
        bump()
        make_backup()


def week_hist():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    out = []
    for i in range(6):
        d = monday + datetime.timedelta(days=i)
        out.append(DB["history"].get(d.isoformat()) if d < today else None)
    return out


def make_session(user):
    for tok in [t for t, s in DB["sessions"].items() if s["exp"] < now()]:
        del DB["sessions"][tok]
    token = secrets.token_urlsafe(32)
    DB["sessions"][token] = {"uid": user["id"], "exp": now() + SESSION_DAYS * 86400}
    return token


def revoke_sessions(user_id, keep=None):
    for tok in [t for t, s in DB["sessions"].items() if s["uid"] == user_id and t != keep]:
        del DB["sessions"][tok]


def get_user(headers):
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, None
    token = auth[7:].strip()
    session = DB["sessions"].get(token)
    if not session:
        return None, None
    if session["exp"] < now():
        del DB["sessions"][token]
        return None, None
    user = DB["users"].get(session["uid"])
    if not user or not user["active"] or user["role"] not in ("staff", "admin"):
        return None, None
    return user, token


def online_ids():
    return sorted(uid for uid, u in DB["users"].items()
                  if u["role"] == "staff" and u["active"] and now() - SEEN.get(uid, 0) < ONLINE_SECS)


def version_for(user):
    v = str(VERSION[0])
    if user["role"] == "admin":
        v += "-" + ",".join(online_ids())
    return v


def public_user(u):
    return {"id": u["id"], "name": u["name"], "role": u["role"], "email": u["email"],
            "phone": u["phone"], "must_change": bool(u["must_change"])}


def find_media(name):
    """Look in media/ first, then next to server.py, so the video works either way it was uploaded."""
    for folder in (MEDIA_DIR, HERE):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def promo():
    for name in PROMO_NAMES:
        path = find_media(name)
        if path and os.path.getsize(path) > 0:
            return {"src": "/media/{}?v={}".format(name, int(os.path.getmtime(path))), "type": MEDIA_TYPES[os.path.splitext(name)[1]]}
    return None


def public_order(o):
    return {"id": o["id"], "status": o["status"], "pieces": o["pieces"], "extra": o["extra"],
            "pickup": o["pickup"], "pay": o["pay"], "total": o["total"],
            "created": o["created"], "updated": o["updated"]}


def staff_order(o):
    return {k: v for k, v in o.items() if k != "track"}


def find_order(order_id):
    for o in DB["orders"]:
        if o["id"] == order_id:
            return o
    return None


def owned_order(item):
    if not isinstance(item, dict):
        return None
    order = find_order(item.get("id"))
    if order is None or not order.get("track"):
        return None
    given = str(item.get("token") or "").encode("utf-8")
    if not hmac.compare_digest(str(order["track"]).encode("utf-8"), given):
        return None
    return order


def make_order(name, phone, address, pieces, extra, pickup, pay, source):
    order = {
        "id": DB["next_order_id"], "source": source, "name": name, "phone": phone, "address": address,
        "pieces": pieces, "extra": extra, "pickup": pickup, "pay": pay, "status": "new",
        "total": order_total(pieces, extra), "created": now(), "updated": now(),
        "handled_by": None, "track": secrets.token_hex(8),
    }
    DB["next_order_id"] += 1
    DB["orders"].append(order)
    return order


def api_public(user, body, token, query):
    return 200, {"promo": promo(), "config": CONFIG}


def build_state(user):
    p = {"version": version_for(user), "config": CONFIG, "me": public_user(user), "promo": promo()}
    cutoff = now() - 86400
    p["orders"] = [staff_order(o) for o in DB["orders"] if o["status"] in ACTIVE_STATUSES or o["updated"] > cutoff]
    p["cards"] = DB["cards"]
    p["stock"] = DB["stock"]
    p["sold_today"] = DB["sold_today"]
    p["extra_rev"] = DB["extra_rev"]
    p["week_hist"] = week_hist()
    if user["role"] == "admin":
        online = set(online_ids())
        p["staff"] = [
            {"id": u["id"], "name": u["name"], "email": u["email"], "phone": u["phone"],
             "active": u["active"], "online": u["id"] in online, "last_login": u["last_login"]}
            for u in DB["users"].values() if u["role"] == "staff"
        ]
        p["activity"] = list(reversed(DB["activity"][-200:]))
        p["customers"] = len({o["phone"] for o in DB["orders"] if o.get("phone")})
    return p


def ok(user, **extra):
    data = {"ok": True, "state": build_state(user)}
    data.update(extra)
    return 200, data


def err(status, message):
    return status, {"error": message}


def throttled(key):
    f = FAILS.get(key)
    return bool(f and f["until"] > now())


def register_fail(key):
    f = FAILS.setdefault(key, {"n": 0, "until": 0})
    f["n"] += 1
    if f["n"] >= 5:
        f["until"] = now() + 60
        f["n"] = 0


def api_login(user, body, token, query):
    raw = str(body.get("identifier") or "").strip()
    kind, value = parse_identifier(raw)
    password = body.get("password")
    key = value or raw.lower()
    if throttled(key):
        return err(429, "Too many tries. Wait a minute and try again.")
    account = find_user(kind, value) if kind else None
    if account is not None and account["role"] not in STAFF:
        account = None
    good = isinstance(password, str) and check_pw(account, password)
    if not good:
        register_fail(key)
        return err(400, "Wrong email, mobile number or password.")
    if not account["active"]:
        return err(403, "This account is disabled. Please ask the owner.")
    FAILS.pop(key, None)
    account["last_login"] = now()
    SEEN[account["id"]] = now()
    session = make_session(account)
    log(account, "signed in")
    bump()
    return ok(account, token=session)


def api_logout(user, body, token, query):
    DB["sessions"].pop(token, None)
    SEEN.pop(user["id"], None)
    log(user, "signed out")
    bump()
    return 200, {"ok": True}


def api_state(user, body, token, query):
    SEEN[user["id"]] = now()
    current = version_for(user)
    if query.get("v", [""])[0] == current:
        return 200, {"unchanged": True}
    return 200, build_state(user)


def api_password_change(user, body, token, query):
    old, new = body.get("old"), body.get("new")
    if not isinstance(old, str) or not check_pw(user, old):
        return err(400, "Your current password is not correct.")
    problem = password_problem(new)
    if problem:
        return err(400, problem)
    if new == old:
        return err(400, "Choose a password that is different from the current one.")
    user["salt"], user["hash"] = hash_pw(new)
    user["must_change"] = False
    revoke_sessions(user["id"], keep=token)
    log(user, "changed their password")
    bump()
    return ok(user)


def send_reset_code(user, kind, value, code):
    if kind == "email":
        send_mail(value, "Your UbeKeso Cart password reset code: " + code,
                  "Your UbeKeso Cart password reset code is {}.\nIt works for {} minutes. "
                  "If you did not ask for it, ignore this email.\n".format(code, RESET_MINUTES))
    else:
        print("[password reset] SMS to {} -> code {} (valid {} min)".format(value, code, RESET_MINUTES))


def api_forgot_request(user, body, token, query):
    kind, value = parse_identifier(body.get("identifier"))
    if not kind:
        return err(400, "Enter a valid email or mobile number.")
    recent = [t for t in RESET_REQUESTS.get(value, []) if t > now() - 600]
    if len(recent) >= 5:
        return err(429, "Too many requests. Please wait a few minutes.")
    RESET_REQUESTS[value] = recent + [now()]
    out = {"ok": True,
           "message": "If an account exists for that {}, a 6-digit code has been sent.".format(
               "email" if kind == "email" else "number")}
    account = find_user(kind, value)
    if account and account["active"] and account["role"] in STAFF:
        code = "{:06d}".format(secrets.randbelow(1000000))
        RESET_CODES[account["id"]] = {"code": code, "exp": now() + RESET_MINUTES * 60, "tries": 0}
        send_reset_code(account, kind, value, code)
        if show_demo_code():
            out["demo_code"] = code
    return 200, out


def api_forgot_reset(user, body, token, query):
    bad = "That code is not valid or has expired. Ask for a new one."
    kind, value = parse_identifier(body.get("identifier"))
    code = str(body.get("code") or "").strip()
    account = find_user(kind, value) if kind else None
    entry = RESET_CODES.get(account["id"]) if account else None
    if not entry or entry["exp"] < now():
        return err(400, bad)
    entry["tries"] += 1
    if entry["tries"] > 5:
        del RESET_CODES[account["id"]]
        return err(400, bad)
    if not hmac.compare_digest(entry["code"], code):
        return err(400, bad)
    problem = password_problem(body.get("password"))
    if problem:
        return err(400, problem)
    account["salt"], account["hash"] = hash_pw(body["password"])
    account["must_change"] = False
    del RESET_CODES[account["id"]]
    revoke_sessions(account["id"])
    log(account, "reset their password")
    bump()
    return 200, {"ok": True}


def to_int(value, low, high):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


def api_order_public(user, body, token, query):
    name = clean_name(body.get("name"))
    phone = norm_phone(body.get("phone"))
    address = clean_address(body.get("address"))
    pieces = to_int(body.get("pieces"), 1, MAX_PIECES)
    pickup = str(body.get("pickup") or "")
    extra = bool(body.get("extra"))
    pay = body.get("pay") if body.get("pay") in ("cash", "ewallet") else "cash"
    if not name:
        return err(400, "Enter your name (2 to 60 characters).")
    if not phone:
        return err(400, "Enter a valid mobile number like 09171234567.")
    if not address:
        return err(400, "Enter your complete address (at least 5 characters).")
    if pieces is None:
        return err(400, "Choose between 1 and {} pieces.".format(MAX_PIECES))
    if not TIME_RE.match(pickup):
        return err(400, "Choose a pickup time.")
    ip = str(body.get("_ip") or "")
    recent = [t for t in ORDER_REQUESTS.get(ip, []) if t > now() - 600]
    if len(recent) >= 20:
        return err(429, "Too many orders from this device. Please wait a few minutes.")
    waiting = len([o for o in DB["orders"] if o.get("phone") == phone and o["status"] == "new"])
    if waiting >= 5:
        return err(429, "You already have 5 orders waiting. Please wait for the cart to start them.")
    ORDER_REQUESTS[ip] = recent + [now()]
    order = make_order(name, phone, address, pieces, extra, pickup, pay, "online")
    log({"id": None, "name": name, "role": "customer"},
        "placed order #{} ({} pcs, pickup {})".format(order["id"], pieces, pickup))
    bump()
    return 200, {"ok": True, "order_id": order["id"], "track": order["track"], "order": public_order(order)}


def api_order_track(user, body, token, query):
    wanted = body.get("orders")
    if not isinstance(wanted, list):
        return err(400, "Bad request.")
    cutoff = now() - 86400
    out = []
    for item in wanted[:20]:
        order = owned_order(item)
        if order is not None and (order["status"] in ACTIVE_STATUSES or order["updated"] > cutoff):
            out.append(public_order(order))
    return 200, {"orders": out}


def api_order_cancel_public(user, body, token, query):
    order = owned_order(body)
    if order is None:
        return err(404, "Order not found.")
    if order["status"] != "new":
        return err(400, "Only orders that have not started can be cancelled.")
    order["status"] = "cancelled"
    order["updated"] = now()
    log({"id": None, "name": order["name"], "role": "customer"}, "cancelled order #{}".format(order["id"]))
    bump()
    return 200, {"ok": True, "message": "Order #{} cancelled.".format(order["id"])}


def api_order_create(user, body, token, query):
    pieces = to_int(body.get("pieces"), 1, MAX_PIECES)
    pickup = str(body.get("pickup") or "")
    extra = bool(body.get("extra"))
    pay = body.get("pay") if body.get("pay") in ("cash", "ewallet") else "cash"
    if pieces is None:
        return err(400, "Choose between 1 and {} pieces.".format(MAX_PIECES))
    if not TIME_RE.match(pickup):
        return err(400, "Choose a pickup time.")
    name = clean_name(body.get("name"))
    if not name:
        return err(400, "Enter the customer's name.")
    phone_raw = str(body.get("phone") or "").strip()
    phone = norm_phone(phone_raw) if phone_raw else ""
    if phone is None:
        return err(400, "Enter a valid mobile number like 09171234567.")
    address_raw = str(body.get("address") or "").strip()
    address = clean_address(address_raw) if address_raw else ""
    if address is None:
        return err(400, "The address needs at least 5 characters.")
    order = make_order(name, phone, address, pieces, extra, pickup, pay, "walk-in")
    log(user, "added a pre-order for {} (#{}, {} pcs)".format(name, order["id"], pieces))
    bump()
    return ok(user, order_id=order["id"])


def api_order_action(user, body, token, query):
    order = find_order(body.get("id"))
    action = body.get("action")
    if order is None:
        return err(404, "Order not found.")
    if action == "cancel":
        if order["status"] != "new":
            return err(400, "Only orders that have not started can be cancelled.")
        order["status"] = "cancelled"
        order["updated"] = now()
        log(user, "cancelled order #{} ({})".format(order["id"], order["name"]))
        bump()
        return ok(user, message="Order #{} cancelled.".format(order["id"]))
    if action != "next":
        return err(400, "Unknown action.")
    status = order["status"]
    if status == "new":
        order["status"] = "frying"
        order["handled_by"] = user["name"]
        deduct_stock(order["pieces"])
        message = "Frying started for {}.".format(order["name"])
    elif status == "frying":
        order["status"] = "ready"
        message = "{}'s order is ready.".format(order["name"])
    elif status == "ready":
        order["status"] = "done"
        DB["sold_today"] += order["pieces"]
        if order["extra"]:
            DB["extra_rev"] += order["pieces"] * CONFIG["extra_cheese_price"]
        if order.get("phone"):
            add_stamp(card_for_phone(order["phone"], order["name"]))
        message = "Picked up and paid. {} added to today's sales.".format(peso(order["total"]))
    else:
        return err(400, "This order is already finished.")
    order["updated"] = now()
    log(user, "moved order #{} ({}) to {}".format(order["id"], order["name"], order["status"]))
    bump()
    return ok(user, message=message)


def api_sale(user, body, token, query):
    qty = to_int(body.get("qty"), 1, 200)
    if qty is None:
        return err(400, "Enter a quantity of 1 or more.")
    extra = bool(body.get("extra"))
    pay = "ewallet" if body.get("pay") == "ewallet" else "cash"
    total = order_total(qty, extra)
    DB["sold_today"] += qty
    if extra:
        DB["extra_rev"] += qty * CONFIG["extra_cheese_price"]
    deduct_stock(qty)
    stamp_msg = ""
    card = card_by_id(body.get("card_id")) if body.get("card_id") else None
    if card:
        if add_stamp(card):
            stamp_msg = "Stamp added. {} of {} on this loyalty card.".format(card["stamps"], CONFIG["stamps_for_free"])
        else:
            stamp_msg = "This card is full. Redeem the free piece on the Loyalty tab."
    receipt = {"qty": qty, "extra": extra, "total": total, "pay": pay, "stamp_msg": stamp_msg,
               "ref": "EW-{}".format(secrets.randbelow(900000) + 100000)}
    log(user, "charged a sale: {} pcs, {} ({})".format(qty, peso(total), "e-wallet" if pay == "ewallet" else "cash"))
    bump()
    return ok(user, receipt=receipt)


def api_card_create(user, body, token, query):
    name = clean_name(body.get("name"))
    if not name:
        return err(400, "Enter the customer's name.")
    card = create_card(name)
    log(user, "created loyalty card {} for {}".format(card["id"], name))
    bump()
    return ok(user, card_id=card["id"])


def api_card_stamp(user, body, token, query):
    card = card_by_id(body.get("id"))
    if card is None:
        return err(404, "Card not found.")
    if not add_stamp(card):
        return err(400, "This card is full. Redeem the free piece first.")
    log(user, "added a stamp to {} ({} of {})".format(card["name"], card["stamps"], CONFIG["stamps_for_free"]))
    bump()
    return ok(user, message="Stamp added. {} of {}.".format(card["stamps"], CONFIG["stamps_for_free"]))


def api_card_redeem(user, body, token, query):
    card = card_by_id(body.get("id"))
    if card is None:
        return err(404, "Card not found.")
    if card["stamps"] < CONFIG["stamps_for_free"]:
        return err(400, "This card needs {} stamps first.".format(CONFIG["stamps_for_free"]))
    card["stamps"] = 0
    log(user, "redeemed a free piece for {}".format(card["name"]))
    bump()
    return ok(user, message="Free piece redeemed. Card is back to 0 of {}.".format(CONFIG["stamps_for_free"]))


def api_stock(user, body, token, query):
    index = to_int(body.get("index"), 0, len(DB["stock"]) - 1)
    amount = to_int(body.get("amount"), 1, 10000)
    mode = body.get("mode")
    if index is None or mode not in ("delivery", "usage"):
        return err(400, "Choose an ingredient.")
    if amount is None:
        return err(400, "Enter a number of 1 or more.")
    item = DB["stock"][index]
    if mode == "delivery":
        item["left"] += amount
        message = "{} +{} pieces.".format(item["name"], amount)
        log(user, "added a delivery: {} +{} pieces".format(item["name"], amount))
    else:
        item["left"] = max(0, item["left"] - amount)
        message = "{} -{} pieces.".format(item["name"], amount)
        log(user, "logged usage: {} -{} pieces".format(item["name"], amount))
    bump()
    return ok(user, message=message)


def api_staff_create(user, body, token, query):
    name = clean_name(body.get("name"))
    value, gmail_error = check_gmail(body.get("identifier"))
    password = body.get("password")
    if not name:
        return err(400, "Enter the staff member's name.")
    if gmail_error:
        return err(400, gmail_error)
    problem = password_problem(password)
    if problem:
        return err(400, problem)
    if find_user("email", value):
        return err(409, "An account with this Gmail already exists.")
    staff = new_user(name, "staff", "email", value, password, must_change=True, created_by=user["id"])
    log(user, "created a staff account for {}".format(name))
    bump()
    return ok(user, staff_id=staff["id"])


def api_staff_active(user, body, token, query):
    target = DB["users"].get(body.get("id"))
    if target is None or target["role"] != "staff":
        return err(404, "Staff account not found.")
    active = bool(body.get("active"))
    target["active"] = active
    if not active:
        revoke_sessions(target["id"])
        SEEN.pop(target["id"], None)
    log(user, "{} the account of {}".format("enabled" if active else "disabled", target["name"]))
    bump()
    return ok(user, message="{} {}.".format(target["name"], "enabled" if active else "disabled"))


def api_activity_delete(user, body, token, query):
    before = len(DB["activity"])
    if body.get("all") is True:
        DB["activity"] = []
    else:
        ids = body.get("ids")
        if not isinstance(ids, list) or not ids:
            return err(400, "Choose which entries to delete.")
        wanted = set(str(i) for i in ids)
        DB["activity"] = [a for a in DB["activity"] if str(a.get("id")) not in wanted]
    removed = before - len(DB["activity"])
    bump()
    return ok(user, message="{} entr{} deleted.".format(removed, "y" if removed == 1 else "ies"))


STAFF = ("staff", "admin")
ADMIN = ("admin",)

ROUTES = {
    ("GET", "/api/public"): (None, api_public),
    ("POST", "/api/order/public"): (None, api_order_public),
    ("POST", "/api/order/track"): (None, api_order_track),
    ("POST", "/api/order/cancel"): (None, api_order_cancel_public),
    ("POST", "/api/login"): (None, api_login),
    ("POST", "/api/forgot/request"): (None, api_forgot_request),
    ("POST", "/api/forgot/reset"): (None, api_forgot_reset),
    ("POST", "/api/logout"): (STAFF, api_logout),
    ("GET", "/api/state"): (STAFF, api_state),
    ("POST", "/api/password/change"): (STAFF, api_password_change),
    ("POST", "/api/orders"): (STAFF, api_order_create),
    ("POST", "/api/orders/action"): (STAFF, api_order_action),
    ("POST", "/api/sale"): (STAFF, api_sale),
    ("POST", "/api/cards"): (STAFF, api_card_create),
    ("POST", "/api/cards/stamp"): (STAFF, api_card_stamp),
    ("POST", "/api/cards/redeem"): (STAFF, api_card_redeem),
    ("POST", "/api/stock"): (STAFF, api_stock),
    ("POST", "/api/staff"): (ADMIN, api_staff_create),
    ("POST", "/api/staff/active"): (ADMIN, api_staff_active),
    ("POST", "/api/activity/delete"): (ADMIN, api_activity_delete),
}


STATIC = {
    "/": "index.html", "/index.html": "index.html", "/style.css": "style.css",
    "/extra.css": "extra.css", "/main.py": "main.py", "/pyscript.toml": "pyscript.toml",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def end_headers(self):
        if not getattr(self, "_media", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _serve_media(self, name, head=False):
        ext = os.path.splitext(name)[1].lower()
        if not (MEDIA_NAME_RE.match(name) and ext in MEDIA_TYPES):
            return self.send_error(404)
        full = find_media(name)
        if full is None:
            return self.send_error(404)
        size = os.path.getsize(full)
        start, end, status = 0, size - 1, 200
        wanted = self.headers.get("Range")
        if wanted and size:
            m = re.match(r"^bytes=(\d*)-(\d*)$", wanted.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */{}".format(size))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        self._media = True
        self.send_response(status)
        self.send_header("Content-Type", MEDIA_TYPES[ext])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=3600")
        if status == 206:
            self.send_header("Content-Range", "bytes {}-{}/{}".format(start, end, size))
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.end_headers()
        if head:
            return
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, data):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _api(self, method):
        parsed = urllib.parse.urlparse(self.path)
        route = ROUTES.get((method, parsed.path))
        if route is None:
            return self._json(404, {"error": "Not found."})
        roles, fn = route
        body = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length > 65536:
                return self._json(413, {"error": "Request too large."})
            try:
                body = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"error": "Bad request."})
        body["_ip"] = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]
        try:
            with LOCK:
                roll_day()
                user = token = None
                if roles is not None:
                    user, token = get_user(self.headers)
                    if user is None:
                        return self._json(401, {"error": "Please sign in again."})
                    if user["role"] not in roles:
                        return self._json(403, {"error": "You do not have access to that."})
                status, data = fn(user, body, token, urllib.parse.parse_qs(parsed.query))
        except Exception:
            traceback.print_exc()
            return self._json(500, {"error": "Something went wrong on the server."})
        self._json(status, data)

    def _static_or_redirect(self, head=False):
        path = urllib.parse.urlparse(self.path).path
        if path == "/favicon.ico":
            return self._redirect("/media/logo-icon.png")
        if path in STATIC:
            self.path = "/" + STATIC[path]
            return (super().do_HEAD if head else super().do_GET)()
        # Any other address (old links, typos, /home, /index) goes straight to the landing page.
        return self._redirect("/")

    def _redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._media = False
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api("GET")
        if path.startswith("/media/"):
            return self._serve_media(urllib.parse.unquote(path[len("/media/"):]))
        return self._static_or_redirect()

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path.startswith("/api/"):
            return self._api("POST")
        self.send_error(404)

    def do_HEAD(self):
        self._media = False
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            return self.send_error(405)
        if path.startswith("/media/"):
            return self._serve_media(urllib.parse.unquote(path[len("/media/"):]), head=True)
        return self._static_or_redirect(head=True)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(host, start_port):
    for port in range(start_port, start_port + 20):
        try:
            return Server((host, port), Handler), port
        except OSError:
            continue
    raise SystemExit("Could not find a free port from {} to {}.".format(start_port, start_port + 19))
