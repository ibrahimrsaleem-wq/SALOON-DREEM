from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "saloon_dreem.db"))).expanduser()
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Gaza")
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "").strip()
if not TOKEN_SECRET:
    # Stable per-installation secret; explicitly setting TOKEN_SECRET remains preferred in production.
    _secret_path = DATA_DIR / ".token-secret"
    try:
        TOKEN_SECRET = _secret_path.read_text(encoding="utf-8").strip()
    except OSError:
        TOKEN_SECRET = ""
    if not TOKEN_SECRET:
        TOKEN_SECRET = secrets.token_urlsafe(48)
        try:
            _secret_path.write_text(TOKEN_SECRET, encoding="utf-8")
            try:
                os.chmod(_secret_path, 0o600)
            except OSError:
                # Windows ACLs manage access differently; keep normal Windows startup working.
                pass
        except OSError as exc:
            raise RuntimeError(
                "تعذر حفظ مفتاح الجلسات. تأكد أن مجلد DATA_DIR قابل للكتابة أو عيّن TOKEN_SECRET آمنًا في البيئة."
            ) from exc
if len(TOKEN_SECRET) < 32:
    raise RuntimeError("TOKEN_SECRET قصير جدًا؛ استخدم قيمة عشوائية لا تقل عن 32 حرفًا.")
try:
    TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
except ValueError as exc:
    raise RuntimeError("TOKEN_HOURS يجب أن يكون رقمًا صحيحًا من 1 إلى 168.") from exc
if not 1 <= TOKEN_HOURS <= 168:
    raise RuntimeError("TOKEN_HOURS يجب أن يكون بين 1 و168 ساعة.")
APP_VERSION = "1.2.1"

# Small process-local guard for local/single-instance installations. Production deployments
# with multiple workers should also enforce rate limits at their reverse proxy/API gateway.
_RATE_EVENTS: dict[str, deque[float]] = {}
_RATE_LOCK = threading.Lock()

def enforce_rate_limit(request: Request, *, bucket: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    host = request.client.host if request.client else "unknown"
    key = f"{bucket}:{host}"
    with _RATE_LOCK:
        events = _RATE_EVENTS.setdefault(key, deque())
        while events and now - events[0] >= window_seconds:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])))
            raise HTTPException(429, detail="محاولات كثيرة خلال وقت قصير. حاول مجددًا بعد قليل.", headers={"Retry-After": str(retry_after)})
        events.append(now)
        if len(_RATE_EVENTS) > 2048:
            stale = [name for name, values in _RATE_EVENTS.items() if not values or now - values[-1] >= 3600]
            for name in stale:
                _RATE_EVENTS.pop(name, None)

def validate_iso_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"قيمة التاريخ في {field_name} غير صالحة. استخدم YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=422, detail=f"صيغة التاريخ في {field_name} يجب أن تكون YYYY-MM-DD.")
    return value

def safe_csv_cell(value: Any) -> Any:
    """Neutralize spreadsheet formula prefixes in customer-controlled text exported to CSV."""
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SALOON DREEM API",
    description="Arabic-first salon management, appointment scheduling, team, customers and cashbook.",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)
_cors_origins = os.getenv("CORS_ORIGINS", "").strip()
if _cors_origins:
    _allowed_origins = [origin.strip() for origin in _cors_origins.split(",") if origin.strip()]
else:
    # The Capacitor Android build serves local assets from this origin while calling
    # a separately hosted HTTPS API. Same-origin web installs need no CORS entry.
    _allowed_origins = ["https://localhost", "capacitor://localhost"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@contextmanager
def db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_local() -> datetime:
    try:
        return datetime.now(ZoneInfo(TIMEZONE))
    except Exception:
        return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().replace(tzinfo=None, microsecond=0).isoformat()


def init_db() -> None:
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK(duration_minutes > 0),
                price REAL NOT NULL DEFAULT 0 CHECK(price >= 0),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS barbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                specialty TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                service_id INTEGER NOT NULL REFERENCES services(id),
                barber_id INTEGER REFERENCES barbers(id),
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','completed','cancelled')),
                price REAL NOT NULL DEFAULT 0 CHECK(price >= 0),
                payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid','paid')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                transaction_date TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                appointment_id INTEGER REFERENCES appointments(id),
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_transaction_appointment_income
                ON transactions(appointment_id) WHERE appointment_id IS NOT NULL AND kind = 'income';
            CREATE INDEX IF NOT EXISTS ix_appointments_start ON appointments(start_at);
            CREATE INDEX IF NOT EXISTS ix_appointments_barber_start ON appointments(barber_id, start_at, end_at);
            CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions(transaction_date);
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        service_count = con.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        if service_count == 0:
            defaults = [
                ("قصة شعر", "قصة كلاسيكية أو عصرية", 30, 25.0, 1, now_iso()),
                ("تهذيب اللحية", "تحديد وتهذيب اللحية", 20, 15.0, 1, now_iso()),
                ("قصة شعر + لحية", "جلسة متكاملة", 45, 35.0, 1, now_iso()),
                ("حلاقة أطفال", "قصة شعر للأطفال", 25, 20.0, 1, now_iso()),
                ("عناية بالبشرة", "تنظيف وعناية أساسية", 30, 30.0, 1, now_iso()),
            ]
            con.executemany(
                "INSERT INTO services(name,description,duration_minutes,price,active,created_at) VALUES(?,?,?,?,?,?)",
                defaults,
            )
        settings_defaults = {
            "business_name": "SALOON DREEM",
            "currency": "ILS",
            "phone": "",
            "address": "",
            "open_time": "09:00",
            "close_time": "22:00",
            "theme": "dark",
        }
        for key, value in settings_defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))


# ---- request models -------------------------------------------------------
class SetupInput(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(default="SALOON DREEM", min_length=2, max_length=100)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class PasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ServiceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=400)
    duration_minutes: int = Field(default=30, ge=5, le=480)
    price: float = Field(ge=0, le=1000000)
    active: bool = True


class BarberInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=40)
    specialty: str = Field(default="", max_length=120)
    active: bool = True


class CustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=5, max_length=40)
    email: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=1000)


class AppointmentInput(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    customer_phone: str = Field(min_length=5, max_length=40)
    customer_email: str = Field(default="", max_length=160)
    service_id: int = Field(gt=0)
    barber_id: Optional[int] = Field(default=None, gt=0)
    start_at: str = Field(min_length=16, max_length=30)
    notes: str = Field(default="", max_length=1000)
    status: str = Field(default="confirmed", pattern=r"^(pending|confirmed)$")


class AppointmentPatch(BaseModel):
    status: Optional[str] = Field(default=None, pattern=r"^(pending|confirmed|completed|cancelled)$")
    notes: Optional[str] = Field(default=None, max_length=1000)
    start_at: Optional[str] = Field(default=None, min_length=16, max_length=30)
    barber_id: Optional[int] = None


class TransactionInput(BaseModel):
    kind: str = Field(pattern=r"^(income|expense)$")
    category: str = Field(min_length=2, max_length=100)
    amount: float = Field(gt=0, le=100000000)
    transaction_date: str = Field(min_length=10, max_length=10)
    note: str = Field(default="", max_length=1000)


class SettingsInput(BaseModel):
    settings: dict[str, str]


class PublicAppointmentInput(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    customer_phone: str = Field(min_length=5, max_length=40)
    service_id: int = Field(gt=0)
    barber_id: Optional[int] = Field(default=None, gt=0)
    start_at: str = Field(min_length=16, max_length=30)
    notes: str = Field(default="", max_length=500)


# ---- authentication -------------------------------------------------------
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_text, expected_text = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(expected_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def issue_token(user: sqlite3.Row) -> str:
    password_hash = str(user["password_hash"])
    payload = {
        "sub": int(user["id"]),
        "username": user["username"],
        "exp": int((now_local() + timedelta(hours=TOKEN_HOURS)).timestamp()),
        # Bind the session to the active password hash so password changes revoke old tokens.
        "pwdv": hashlib.sha256(password_hash.encode("utf-8")).hexdigest(),
    }
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + b64url(signature)


def decode_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = b64url(hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if int(payload.get("exp", 0)) <= int(now_local().timestamp()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail="انتهت الجلسة أو أن رمز الدخول غير صالح. سجّل الدخول مجددًا.") from exc


def current_user(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="يرجى تسجيل الدخول أولًا.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    with db() as con:
        user = con.execute("SELECT id, username, created_at, password_hash FROM users WHERE id=?", (payload["sub"],)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="الحساب غير موجود.")
    current_password_version = hashlib.sha256(user["password_hash"].encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(payload.get("pwdv", "")), current_password_version):
        raise HTTPException(status_code=401, detail="تم تغيير كلمة المرور. سجّل الدخول من جديد.")
    return {"id": user["id"], "username": user["username"], "created_at": user["created_at"]}


def require_setup_complete() -> None:
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        raise HTTPException(status_code=409, detail="أنشئ حساب المدير أولًا من شاشة الإعداد الأولي.")


def as_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def clean_money(value: float) -> float:
    return round(float(value), 2)


def parse_local_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
        return parsed.replace(second=0, microsecond=0)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="صيغة التاريخ والوقت غير صحيحة.") from exc


def ensure_slot(con: sqlite3.Connection, barber_id: int, start_at: str, end_at: str, exclude_id: Optional[int] = None) -> None:
    sql = """SELECT id FROM appointments WHERE barber_id=? AND status NOT IN ('cancelled')
             AND start_at < ? AND end_at > ?"""
    params: list[Any] = [barber_id, end_at, start_at]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    conflict = con.execute(sql + " LIMIT 1", params).fetchone()
    if conflict:
        raise HTTPException(status_code=409, detail="هذا الموعد يتعارض مع حجز آخر للحلاق المختار. اختر وقتًا أو حلاقًا آخر.")


def choose_barber(con: sqlite3.Connection, barber_id: Optional[int], start: datetime, end: datetime, exclude_id: Optional[int] = None) -> int:
    start_s, end_s = start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")
    if barber_id is not None:
        barber = con.execute("SELECT id FROM barbers WHERE id=? AND active=1", (barber_id,)).fetchone()
        if not barber:
            raise HTTPException(status_code=422, detail="الحلاق المحدد غير متاح أو غير موجود.")
        ensure_slot(con, barber_id, start_s, end_s, exclude_id)
        return barber_id
    barbers = con.execute("SELECT id FROM barbers WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()
    for barber in barbers:
        try:
            ensure_slot(con, int(barber["id"]), start_s, end_s, exclude_id)
            return int(barber["id"])
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    if not barbers:
        raise HTTPException(status_code=422, detail="أضف حلاقًا نشطًا قبل استقبال الحجوزات.")
    raise HTTPException(status_code=409, detail="لا يوجد حلاق متاح في هذا الوقت. اختر موعدًا آخر.")


def appointment_select_sql() -> str:
    return """SELECT a.id,a.customer_id,a.service_id,a.barber_id,a.start_at,a.end_at,a.status,a.price,a.payment_status,a.notes,a.created_at,a.updated_at,
              c.name AS customer_name,c.phone AS customer_phone,s.name AS service_name,s.duration_minutes,
              b.name AS barber_name
              FROM appointments a JOIN customers c ON c.id=a.customer_id
              JOIN services s ON s.id=a.service_id LEFT JOIN barbers b ON b.id=a.barber_id"""


def get_settings(con: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in con.execute("SELECT key,value FROM settings").fetchall()}


def ensure_business_hours(con: sqlite3.Connection, start: datetime, end: datetime) -> None:
    """Keep appointments within configured opening hours (including overnight schedules)."""
    stored = get_settings(con)
    try:
        opening = datetime.strptime(stored.get("open_time", "09:00"), "%H:%M").time()
        closing = datetime.strptime(stored.get("close_time", "22:00"), "%H:%M").time()
    except ValueError:
        opening, closing = datetime.strptime("09:00", "%H:%M").time(), datetime.strptime("22:00", "%H:%M").time()
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    open_minutes = opening.hour * 60 + opening.minute
    close_minutes = closing.hour * 60 + closing.minute
    if open_minutes < close_minutes:
        valid = start.date() == end.date() and start_minutes >= open_minutes and end_minutes <= close_minutes
    else:
        # Overnight schedule such as 18:00–02:00. An appointment may cross midnight,
        # but its ending time must still be before the configured morning close.
        next_day = start.date() + timedelta(days=1)
        if start_minutes >= open_minutes:
            valid = (
                (end.date() == start.date() and end_minutes <= 24 * 60)
                or (end.date() == next_day and end_minutes <= close_minutes)
            )
        elif start_minutes < close_minutes:
            valid = end.date() == start.date() and end_minutes <= close_minutes
        else:
            valid = False
    if not valid:
        raise HTTPException(status_code=422, detail=f"الموعد خارج ساعات العمل ({stored.get('open_time', '09:00')}–{stored.get('close_time', '22:00')}).")


# ---- public and session endpoints ----------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": "SALOON DREEM", "version": APP_VERSION, "time": now_iso()}


@app.get("/api/setup/status")
def setup_status() -> dict[str, bool]:
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"setup_required": count == 0}


@app.post("/api/setup", status_code=201)
def create_first_admin(payload: SetupInput, request: Request) -> dict[str, Any]:
    enforce_rate_limit(request, bucket="setup", limit=5, window_seconds=3600)
    with db() as con:
        # Serialize first-run setup so concurrent requests cannot create multiple initial admins.
        con.execute("BEGIN IMMEDIATE")
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count:
            raise HTTPException(status_code=409, detail="تم إعداد التطبيق مسبقًا. سجّل الدخول بدلًا من إنشاء مدير جديد.")
        try:
            con.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (payload.username, hash_password(payload.password), now_iso()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="اسم المستخدم مستخدم بالفعل.") from exc
        user = con.execute("SELECT id,username,created_at,password_hash FROM users WHERE username=?", (payload.username,)).fetchone()
        con.execute("UPDATE settings SET value=? WHERE key='business_name'", (payload.business_name.strip(),))
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"], "created_at": user["created_at"]},
    }


@app.post("/api/auth/login")
def login(payload: LoginInput, request: Request) -> dict[str, Any]:
    enforce_rate_limit(request, bucket="login", limit=10, window_seconds=60)
    require_setup_complete()
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (payload.username.strip(),)).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة.")
    return {"access_token": issue_token(user), "token_type": "bearer", "user": {"id": user["id"], "username": user["username"], "created_at": user["created_at"]}}


@app.get("/api/auth/me")
def who_am_i(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"user": user}


@app.post("/api/auth/change-password")
def change_password(payload: PasswordInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    with db() as con:
        row = con.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة.")
        con.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.new_password), user["id"]))
    return {"message": "تم تغيير كلمة المرور وإلغاء الجلسات السابقة. سجّل الدخول مجددًا."}


@app.get("/api/public/services")
def public_services() -> list[dict[str, Any]]:
    with db() as con:
        return [dict(r) for r in con.execute("SELECT id,name,description,duration_minutes,price FROM services WHERE active=1 ORDER BY name").fetchall()]


@app.get("/api/public/barbers")
def public_barbers() -> list[dict[str, Any]]:
    with db() as con:
        return [dict(r) for r in con.execute("SELECT id,name,specialty FROM barbers WHERE active=1 ORDER BY name").fetchall()]


@app.get("/api/public/settings")
def public_settings() -> dict[str, str]:
    with db() as con:
        stored = get_settings(con)
    public_keys = ("business_name", "phone", "address", "open_time", "close_time", "currency")
    return {key: stored.get(key, "") for key in public_keys}


@app.post("/api/public/appointments", status_code=201)
def public_book(payload: PublicAppointmentInput, request: Request) -> dict[str, Any]:
    enforce_rate_limit(request, bucket="public-booking", limit=20, window_seconds=60)
    # This endpoint is for customer booking. The appointment is created as pending for staff review.
    start = parse_local_start(payload.start_at)
    if start < now_local().replace(tzinfo=None) - timedelta(minutes=1):
        raise HTTPException(status_code=422, detail="لا يمكن حجز موعد في وقت مضى.")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        service = con.execute("SELECT * FROM services WHERE id=? AND active=1", (payload.service_id,)).fetchone()
        if not service:
            raise HTTPException(status_code=422, detail="الخدمة غير متاحة.")
        end = start + timedelta(minutes=int(service["duration_minutes"]))
        ensure_business_hours(con, start, end)
        barber_id = choose_barber(con, payload.barber_id, start, end)
        phone = payload.customer_phone.strip()
        customer = con.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if customer:
            customer_id = int(customer["id"])
            con.execute("UPDATE customers SET name=? WHERE id=?", (payload.customer_name.strip(), customer_id))
        else:
            cursor = con.execute("INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)", (payload.customer_name.strip(), phone, now_iso()))
            customer_id = int(cursor.lastrowid)
        stamp = now_iso()
        cursor = con.execute(
            "INSERT INTO appointments(customer_id,service_id,barber_id,start_at,end_at,status,price,notes,created_at,updated_at) VALUES(?,?,?,?,?,'pending',?,?,?,?)",
            (customer_id, service["id"], barber_id, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), service["price"], payload.notes.strip(), stamp, stamp),
        )
        row = con.execute(appointment_select_sql() + " WHERE a.id=?", (cursor.lastrowid,)).fetchone()
    return {"message": "وصل طلب الحجز بنجاح، وسيؤكده الصالون.", "appointment": dict(row)}


# ---- dashboard, appointments and customers -------------------------------
@app.get("/api/dashboard")
def dashboard(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    today = now_local().date().isoformat()
    month = today[:7]
    with db() as con:
        today_count = con.execute("SELECT COUNT(*) FROM appointments WHERE substr(start_at,1,10)=? AND status!='cancelled'", (today,)).fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM appointments WHERE status='pending'").fetchone()[0]
        active_customers = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        monthly_income = con.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='income' AND substr(transaction_date,1,7)=?", (month,)).fetchone()[0]
        monthly_expenses = con.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='expense' AND substr(transaction_date,1,7)=?", (month,)).fetchone()[0]
        upcoming = [dict(r) for r in con.execute(appointment_select_sql() + " WHERE a.start_at>=? AND a.status NOT IN ('cancelled','completed') ORDER BY a.start_at LIMIT 6", (now_iso(),)).fetchall()]
        recent = [dict(r) for r in con.execute(appointment_select_sql() + " ORDER BY a.created_at DESC LIMIT 5").fetchall()]
    return {
        "date": today,
        "metrics": {
            "today_appointments": int(today_count),
            "pending_appointments": int(pending),
            "customers": int(active_customers),
            "monthly_income": clean_money(monthly_income),
            "monthly_expenses": clean_money(monthly_expenses),
            "monthly_net": clean_money(monthly_income - monthly_expenses),
        },
        "upcoming": upcoming,
        "recent": recent,
    }


@app.get("/api/appointments")
def list_appointments(
    date_filter: Optional[str] = Query(default=None, alias="date"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    appointment_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = None,
    limit: int = Query(default=300, ge=1, le=1000),
    user: dict[str, Any] = Depends(current_user),
) -> list[dict[str, Any]]:
    date_filter = validate_iso_date(date_filter, "date")
    start_date = validate_iso_date(start_date, "start_date")
    end_date = validate_iso_date(end_date, "end_date")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="تاريخ بداية البحث يجب ألا يتجاوز تاريخ النهاية.")
    if appointment_status and appointment_status not in {"pending", "confirmed", "completed", "cancelled"}:
        raise HTTPException(status_code=422, detail="حالة الموعد غير صالحة.")
    sql = appointment_select_sql() + " WHERE 1=1"
    params: list[Any] = []
    if date_filter:
        sql += " AND substr(a.start_at,1,10)=?"
        params.append(date_filter)
    if start_date:
        sql += " AND substr(a.start_at,1,10)>=?"
        params.append(start_date)
    if end_date:
        sql += " AND substr(a.start_at,1,10)<=?"
        params.append(end_date)
    if appointment_status:
        sql += " AND a.status=?"
        params.append(appointment_status)
    if q:
        like = f"%{q.strip()}%"
        sql += " AND (c.name LIKE ? OR c.phone LIKE ? OR s.name LIKE ? OR COALESCE(b.name,'') LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY a.start_at LIMIT ?"
    params.append(limit)
    with db() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


@app.post("/api/appointments", status_code=201)
def create_appointment(payload: AppointmentInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    start = parse_local_start(payload.start_at)
    if start < now_local().replace(tzinfo=None) - timedelta(minutes=1):
        raise HTTPException(status_code=422, detail="لا يمكن إنشاء موعد في وقت مضى.")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        service = con.execute("SELECT * FROM services WHERE id=? AND active=1", (payload.service_id,)).fetchone()
        if not service:
            raise HTTPException(status_code=422, detail="الخدمة المحددة غير متاحة.")
        end = start + timedelta(minutes=int(service["duration_minutes"]))
        ensure_business_hours(con, start, end)
        barber_id = choose_barber(con, payload.barber_id, start, end)
        phone = payload.customer_phone.strip()
        customer = con.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if customer:
            customer_id = int(customer["id"])
            con.execute("UPDATE customers SET name=?, email=CASE WHEN ?='' THEN email ELSE ? END WHERE id=?", (payload.customer_name.strip(), payload.customer_email.strip(), payload.customer_email.strip(), customer_id))
        else:
            cursor = con.execute("INSERT INTO customers(name,phone,email,created_at) VALUES(?,?,?,?)", (payload.customer_name.strip(), phone, payload.customer_email.strip(), now_iso()))
            customer_id = int(cursor.lastrowid)
        stamp = now_iso()
        cursor = con.execute(
            "INSERT INTO appointments(customer_id,service_id,barber_id,start_at,end_at,status,price,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (customer_id, service["id"], barber_id, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), payload.status, service["price"], payload.notes.strip(), stamp, stamp),
        )
        row = con.execute(appointment_select_sql() + " WHERE a.id=?", (cursor.lastrowid,)).fetchone()
    return {"appointment": dict(row)}


@app.patch("/api/appointments/{appointment_id}")
def update_appointment(appointment_id: int, payload: AppointmentPatch, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        row = con.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="الموعد غير موجود.")
        if row["payment_status"] == "paid" and payload.status == "cancelled":
            raise HTTPException(status_code=409, detail="الموعد مدفوع. نفّذ إجراء استرداد مالي قبل إلغائه.")
        start_s, end_s, barber_id = row["start_at"], row["end_at"], row["barber_id"]
        if payload.start_at is not None:
            start = parse_local_start(payload.start_at)
            if start < now_local().replace(tzinfo=None) - timedelta(minutes=1):
                raise HTTPException(status_code=422, detail="لا يمكن نقل الموعد إلى وقت مضى.")
            service = con.execute("SELECT duration_minutes FROM services WHERE id=?", (row["service_id"],)).fetchone()
            end = start + timedelta(minutes=int(service["duration_minutes"]))
            ensure_business_hours(con, start, end)
            start_s, end_s = start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")
        if payload.barber_id is not None:
            barber_id = choose_barber(con, payload.barber_id, parse_local_start(start_s), parse_local_start(end_s), exclude_id=appointment_id)
        status_value = payload.status if payload.status is not None else row["status"]
        # Re-check availability whenever an active appointment is moved or reactivated.
        # Previously, a cancelled booking could be re-enabled into an occupied time slot.
        slot_needs_check = status_value != "cancelled" and (
            row["status"] == "cancelled" or payload.start_at is not None or payload.barber_id is not None
        )
        if slot_needs_check:
            if barber_id is None:
                barber_id = choose_barber(con, None, parse_local_start(start_s), parse_local_start(end_s), exclude_id=appointment_id)
            else:
                active_barber = con.execute("SELECT id FROM barbers WHERE id=? AND active=1", (barber_id,)).fetchone()
                if not active_barber:
                    barber_id = choose_barber(con, None, parse_local_start(start_s), parse_local_start(end_s), exclude_id=appointment_id)
                else:
                    ensure_slot(con, int(barber_id), start_s, end_s, exclude_id=appointment_id)
        notes_value = payload.notes if payload.notes is not None else row["notes"]
        con.execute("UPDATE appointments SET start_at=?,end_at=?,barber_id=?,status=?,notes=?,updated_at=? WHERE id=?", (start_s, end_s, barber_id, status_value, notes_value, now_iso(), appointment_id))
        updated = con.execute(appointment_select_sql() + " WHERE a.id=?", (appointment_id,)).fetchone()
    return {"appointment": dict(updated)}


@app.post("/api/appointments/{appointment_id}/pay")
def pay_appointment(appointment_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(appointment_select_sql() + " WHERE a.id=?", (appointment_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="الموعد غير موجود.")
        state = con.execute("SELECT payment_status FROM appointments WHERE id=?", (appointment_id,)).fetchone()[0]
        if state == "paid":
            raise HTTPException(status_code=409, detail="تم تسجيل تحصيل هذا الموعد سابقًا.")
        con.execute("INSERT INTO transactions(kind,category,amount,transaction_date,note,appointment_id,created_at) VALUES('income',?,?,?,?,?,?)", (f"خدمة: {row['service_name']}", row["price"], now_local().date().isoformat(), f"تحصيل من {row['customer_name']}", appointment_id, now_iso()))
        con.execute("UPDATE appointments SET payment_status='paid',status=CASE WHEN status='cancelled' THEN status ELSE 'completed' END,updated_at=? WHERE id=?", (now_iso(), appointment_id))
    return {"message": "تم تسجيل التحصيل وتحديث الإيرادات.", "appointment_id": appointment_id}


@app.get("/api/customers")
def list_customers(q: Optional[str] = None, limit: int = Query(default=500, ge=1, le=1000), user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    sql = """SELECT c.id,c.name,c.phone,c.email,c.notes,c.created_at,COUNT(a.id) AS appointments_count,
             COALESCE(SUM(CASE WHEN a.payment_status='paid' THEN a.price ELSE 0 END),0) AS total_spend,
             MAX(a.start_at) AS last_appointment
             FROM customers c LEFT JOIN appointments a ON a.customer_id=c.id"""
    params: list[Any] = []
    if q:
        like = f"%{q.strip()}%"
        sql += " WHERE c.name LIKE ? OR c.phone LIKE ?"
        params.extend([like, like])
    sql += " GROUP BY c.id ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)
    with db() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


@app.post("/api/customers", status_code=201)
def create_customer(payload: CustomerInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        existing = con.execute("SELECT id FROM customers WHERE phone=?", (payload.phone.strip(),)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="رقم الهاتف مسجل مسبقًا. ابحث عن العميل لتعديل بياناته.")
        cursor = con.execute("INSERT INTO customers(name,phone,email,notes,created_at) VALUES(?,?,?,?,?)", (payload.name, payload.phone.strip(), payload.email.strip(), payload.notes.strip(), now_iso()))
        row = con.execute("SELECT * FROM customers WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"customer": dict(row)}


@app.patch("/api/customers/{customer_id}")
def edit_customer(customer_id: int, payload: CustomerInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        if not con.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone():
            raise HTTPException(status_code=404, detail="العميل غير موجود.")
        try:
            con.execute("UPDATE customers SET name=?,phone=?,email=?,notes=? WHERE id=?", (payload.name, payload.phone.strip(), payload.email.strip(), payload.notes.strip(), customer_id))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="رقم الهاتف مستخدم لدى عميل آخر.") from exc
        row = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    return {"customer": dict(row)}


# ---- barber and service management ---------------------------------------
@app.get("/api/barbers")
def list_barbers(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with db() as con:
        return [dict(r) for r in con.execute("""SELECT b.id,b.name,b.phone,b.specialty,b.active,b.created_at,
                  COUNT(CASE WHEN a.status NOT IN ('cancelled') THEN 1 END) AS appointments_count,
                  COUNT(CASE WHEN a.status='completed' THEN 1 END) AS completed_count
                  FROM barbers b LEFT JOIN appointments a ON a.barber_id=b.id GROUP BY b.id ORDER BY b.active DESC,b.name""").fetchall()]


@app.post("/api/barbers", status_code=201)
def create_barber(payload: BarberInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        cursor = con.execute("INSERT INTO barbers(name,phone,specialty,active,created_at) VALUES(?,?,?,?,?)", (payload.name, payload.phone.strip(), payload.specialty.strip(), int(payload.active), now_iso()))
        row = con.execute("SELECT * FROM barbers WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"barber": dict(row)}


@app.patch("/api/barbers/{barber_id}")
def update_barber(barber_id: int, payload: BarberInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        if not con.execute("SELECT id FROM barbers WHERE id=?", (barber_id,)).fetchone():
            raise HTTPException(status_code=404, detail="الحلاق غير موجود.")
        con.execute("UPDATE barbers SET name=?,phone=?,specialty=?,active=? WHERE id=?", (payload.name, payload.phone.strip(), payload.specialty.strip(), int(payload.active), barber_id))
        row = con.execute("SELECT * FROM barbers WHERE id=?", (barber_id,)).fetchone()
    return {"barber": dict(row)}


@app.delete("/api/barbers/{barber_id}")
def deactivate_barber(barber_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    with db() as con:
        cursor = con.execute("UPDATE barbers SET active=0 WHERE id=?", (barber_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الحلاق غير موجود.")
    return {"message": "تم إيقاف الحلاق دون حذف سجل مواعيده."}


@app.get("/api/services")
def list_services(include_inactive: bool = False, user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with db() as con:
        where = "" if include_inactive else "WHERE s.active=1"
        return [dict(r) for r in con.execute(f"""SELECT s.*,COUNT(a.id) AS bookings_count FROM services s
                  LEFT JOIN appointments a ON a.service_id=s.id {where} GROUP BY s.id ORDER BY s.active DESC,s.name""").fetchall()]


@app.post("/api/services", status_code=201)
def create_service(payload: ServiceInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        cursor = con.execute("INSERT INTO services(name,description,duration_minutes,price,active,created_at) VALUES(?,?,?,?,?,?)", (payload.name, payload.description, payload.duration_minutes, payload.price, int(payload.active), now_iso()))
        row = con.execute("SELECT * FROM services WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"service": dict(row)}


@app.put("/api/services/{service_id}")
def update_service(service_id: int, payload: ServiceInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with db() as con:
        if not con.execute("SELECT id FROM services WHERE id=?", (service_id,)).fetchone():
            raise HTTPException(status_code=404, detail="الخدمة غير موجودة.")
        con.execute("UPDATE services SET name=?,description=?,duration_minutes=?,price=?,active=? WHERE id=?", (payload.name, payload.description, payload.duration_minutes, payload.price, int(payload.active), service_id))
        row = con.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    return {"service": dict(row)}


@app.delete("/api/services/{service_id}")
def deactivate_service(service_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    with db() as con:
        cursor = con.execute("UPDATE services SET active=0 WHERE id=?", (service_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الخدمة غير موجودة.")
    return {"message": "تم إخفاء الخدمة مع الاحتفاظ بالحجوزات السابقة."}


# ---- cashbook and settings -----------------------------------------------
@app.get("/api/finance/summary")
def finance_summary(start_date: Optional[str] = None, end_date: Optional[str] = None, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    start_date = validate_iso_date(start_date, "start_date")
    end_date = validate_iso_date(end_date, "end_date")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="تاريخ بداية التقرير يجب ألا يتجاوز تاريخ النهاية.")
    sql = "SELECT kind,COALESCE(SUM(amount),0) amount FROM transactions WHERE 1=1"
    params: list[Any] = []
    if start_date:
        sql += " AND transaction_date>=?"
        params.append(start_date)
    if end_date:
        sql += " AND transaction_date<=?"
        params.append(end_date)
    sql += " GROUP BY kind"
    with db() as con:
        totals = {r["kind"]: clean_money(r["amount"]) for r in con.execute(sql, params).fetchall()}
        tx_sql = "SELECT t.*,a.id AS linked_appointment_id FROM transactions t LEFT JOIN appointments a ON a.id=t.appointment_id WHERE 1=1"
        if start_date:
            tx_sql += " AND t.transaction_date>=?"
        if end_date:
            tx_sql += " AND t.transaction_date<=?"
        tx_sql += " ORDER BY t.transaction_date DESC,t.id DESC LIMIT 500"
        txs = [dict(r) for r in con.execute(tx_sql, params).fetchall()]
    income = totals.get("income", 0.0)
    expenses = totals.get("expense", 0.0)
    return {"income": income, "expenses": expenses, "net": clean_money(income - expenses), "transactions": txs}


@app.post("/api/finance/transactions", status_code=201)
def create_transaction(payload: TransactionInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.transaction_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="تاريخ الحركة المالية غير صالح.") from exc
    with db() as con:
        cursor = con.execute("INSERT INTO transactions(kind,category,amount,transaction_date,note,created_at) VALUES(?,?,?,?,?,?)", (payload.kind, payload.category.strip(), clean_money(payload.amount), payload.transaction_date, payload.note.strip(), now_iso()))
        row = con.execute("SELECT * FROM transactions WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"transaction": dict(row)}


@app.get("/api/settings")
def read_settings(user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    with db() as con:
        return get_settings(con)


@app.put("/api/settings")
def update_settings(payload: SettingsInput, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    allowed = {"business_name", "currency", "phone", "address", "open_time", "close_time", "theme"}
    if not set(payload.settings).issubset(allowed):
        raise HTTPException(status_code=422, detail="تتضمن الإعدادات حقولًا غير معروفة.")
    values = payload.settings
    if "business_name" in values and len(values["business_name"].strip()) < 2:
        raise HTTPException(status_code=422, detail="اسم الصالون يجب ألا يقل عن حرفين.")
    for key in ("open_time", "close_time"):
        if key in values:
            try:
                datetime.strptime(values[key], "%H:%M")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="صيغة وقت العمل يجب أن تكون HH:MM مثل 09:00.") from exc
    if "theme" in values and values["theme"] not in {"light", "dark"}:
        raise HTTPException(status_code=422, detail="المظهر المسموح هو light أو dark.")
    if "currency" in values and values["currency"] not in {"ILS", "USD", "EUR", "JOD", "SAR", "AED"}:
        raise HTTPException(status_code=422, detail="العملة غير مدعومة.")
    with db() as con:
        for key, value in payload.settings.items():
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value.strip()[:200]))
        return get_settings(con)


@app.get("/api/export/appointments.csv")
def export_appointments(user: dict[str, Any] = Depends(current_user)) -> StreamingResponse:
    with db() as con:
        rows = con.execute(appointment_select_sql() + " ORDER BY a.start_at DESC").fetchall()
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["رقم الحجز", "العميل", "الهاتف", "الخدمة", "الحلاق", "البداية", "النهاية", "الحالة", "السعر", "الدفع", "ملاحظات"])
    status_names = {"pending": "بانتظار التأكيد", "confirmed": "مؤكد", "completed": "مكتمل", "cancelled": "ملغي"}
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in [
            row["id"], row["customer_name"], row["customer_phone"], row["service_name"],
            row["barber_name"] or "—", row["start_at"], row["end_at"],
            status_names.get(row["status"], row["status"]), row["price"],
            "مدفوع" if row["payment_status"] == "paid" else "غير مدفوع", row["notes"],
        ]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=saloon-dreem-appointments.csv"})


# Serve the installable web app after API routes are registered.
FRONTEND_DIR = ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
