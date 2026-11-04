from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest


def create_admin(client):
    response = client.post(
        "/api/setup",
        json={"username": "owner.test", "password": "Strong-Password-123", "business_name": "Dreem Test"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["access_token"]


def create_barber(client, headers, name="Test Barber"):
    response = client.post(
        "/api/barbers",
        headers=headers,
        json={"name": name, "phone": "0599000123", "specialty": "قص شعر", "active": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["barber"]


def booking_payload(client, day, barber_id, phone="0599000999", start="10:00"):
    service = client.get("/api/public/services").json()[0]
    return {
        "customer_name": "Customer Test",
        "customer_phone": phone,
        "service_id": service["id"],
        "barber_id": barber_id,
        "start_at": f"{day}T{start}",
        "notes": "API integration test",
    }


def future_day(module, offset=3):
    return (module.now_local().date() + timedelta(days=offset)).isoformat()


def test_health_setup_login_password_rotation_and_disabled_staff(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "1.3.0"
    assert client.get("/api/setup/status").json()["setup_required"] is True

    headers, old_token = create_admin(client)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/setup/status").json()["setup_required"] is False
    duplicate = client.post(
        "/api/setup",
        json={"username": "other.admin", "password": "Strong-Password-123", "business_name": "Other"},
    )
    assert duplicate.status_code == 409

    changed = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "Strong-Password-123", "new_password": "New-Strong-Password-456"},
    )
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"username": "owner.test", "password": "New-Strong-Password-456"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"

    receptionist = client.post(
        "/api/users", headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"username": "frontdesk", "password": "Reception-123", "role": "receptionist"},
    )
    assert receptionist.status_code == 201, receptionist.text
    user_id = receptionist.json()["user"]["id"]
    disabled = client.patch(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {login.json()['access_token']}"}, json={"active": False})
    assert disabled.status_code == 200
    disabled_login = client.post("/api/auth/login", json={"username": "frontdesk", "password": "Reception-123"})
    assert disabled_login.status_code == 401


def test_booking_payment_refund_customer_lookup_and_csv_safety(client):
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    assert client.get("/api/public/settings").json()["timezone"] == app_module.TIMEZONE
    assert client.get("/api/settings", headers=headers).json()["timezone"] == app_module.TIMEZONE
    day = future_day(app_module)
    payload = booking_payload(client, day, barber["id"])
    payload["customer_name"] = "=2+2"
    service_id = payload["service_id"]
    availability = client.get("/api/public/availability", params={"date": day, "service_id": service_id, "barber_id": barber["id"]})
    assert availability.status_code == 200, availability.text
    assert any(x["start_at"] == f"{day}T10:00" for x in availability.json()["slots"])

    booked = client.post("/api/public/appointments", json=payload)
    assert booked.status_code == 201, booked.text
    appointment = booked.json()["appointment"]
    appointment_id = appointment["id"]
    assert appointment["status"] == "pending"
    assert appointment["payment_status"] == "unpaid"

    looked_up = client.post("/api/public/appointments/lookup", json={"appointment_id": appointment_id, "phone": payload["customer_phone"]})
    assert looked_up.status_code == 200, looked_up.text
    assert looked_up.json()["appointment"]["id"] == appointment_id
    assert "customer_phone" not in looked_up.json()["appointment"]
    assert client.post("/api/public/appointments/lookup", json={"appointment_id": appointment_id, "phone": "0599000000"}).status_code == 404

    conflict = client.post("/api/public/appointments", json=payload)
    assert conflict.status_code == 409, conflict.text
    after_booking = client.get("/api/public/availability", params={"date": day, "service_id": service_id, "barber_id": barber["id"]})
    assert after_booking.status_code == 200
    assert not any(x["start_at"] == f"{day}T10:00" for x in after_booking.json()["slots"])

    paid = client.post(f"/api/appointments/{appointment_id}/pay", headers=headers, json={"payment_method": "card"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["payment_method"] == "card"
    rows = client.get("/api/appointments", headers=headers).json()
    row = next(x for x in rows if x["id"] == appointment_id)
    assert row["status"] == "pending", "Payment must not mark a future service as completed."
    assert row["payment_status"] == "paid"
    assert client.post(f"/api/appointments/{appointment_id}/pay", headers=headers, json={"payment_method": "cash"}).status_code == 409
    assert client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"status": "cancelled"}).status_code == 409

    refund = client.post(f"/api/appointments/{appointment_id}/refund", headers=headers, json={"payment_method": "card", "note": "اختبار الاسترداد"})
    assert refund.status_code == 200, refund.text
    assert refund.json()["payment_method"] == "card"
    assert client.post(f"/api/appointments/{appointment_id}/refund", headers=headers).status_code == 409
    rows = client.get("/api/appointments", headers=headers).json()
    row = next(x for x in rows if x["id"] == appointment_id)
    assert row["refund_status"] == "refunded"
    assert row["status"] == "cancelled", "Refunding a future booking must release its reserved slot."
    assert row["payment_status"] == "paid", "Keep the original collection record; refunds are a separate ledger entry."
    finance = client.get("/api/finance/summary", headers=headers)
    assert finance.status_code == 200
    assert finance.json()["income"] == pytest.approx(finance.json()["expenses"])
    customers = client.get("/api/customers", headers=headers).json()
    customer = next(c for c in customers if c["phone"] == payload["customer_phone"])
    assert customer["total_spend"] == 0

    export = client.get("/api/export/appointments.csv", headers=headers)
    assert export.status_code == 200
    assert "'=2+2" in export.text


def test_refund_of_completed_service_keeps_completed_status(client):
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    day = future_day(app_module, 5)
    booking = client.post(
        "/api/public/appointments",
        json=booking_payload(client, day, barber["id"], "0599000777", "10:00"),
    )
    assert booking.status_code == 201, booking.text
    appointment_id = booking.json()["appointment"]["id"]

    with app_module.db() as con:
        con.execute("UPDATE appointments SET status='completed' WHERE id=?", (appointment_id,))
    paid = client.post(f"/api/appointments/{appointment_id}/pay", headers=headers, json={"payment_method": "cash"})
    assert paid.status_code == 200, paid.text
    refunded = client.post(f"/api/appointments/{appointment_id}/refund", headers=headers, json={"note": "Goodwill adjustment"})
    assert refunded.status_code == 200, refunded.text
    row = next(item for item in client.get("/api/appointments", headers=headers).json() if item["id"] == appointment_id)
    assert row["status"] == "completed"
    assert row["payment_status"] == "paid"
    assert row["refund_status"] == "refunded"


def test_roles_and_barber_data_scope(client):
    from backend.app import main as app_module

    admin_headers, _ = create_admin(client)
    barber_a = create_barber(client, admin_headers, "Barber A")
    barber_b = create_barber(client, admin_headers, "Barber B")
    day = future_day(app_module)
    book_a = client.post("/api/public/appointments", json=booking_payload(client, day, barber_a["id"], "0599000101", "10:00"))
    book_b = client.post("/api/public/appointments", json=booking_payload(client, day, barber_b["id"], "0599000102", "11:00"))
    assert book_a.status_code == 201, book_a.text
    assert book_b.status_code == 201, book_b.text

    barber_account = client.post("/api/users", headers=admin_headers, json={"username": "barber.a", "password": "Barber-Password-123", "role": "barber", "barber_id": barber_a["id"]})
    assert barber_account.status_code == 201, barber_account.text
    receptionist_account = client.post("/api/users", headers=admin_headers, json={"username": "reception.a", "password": "Reception-Password-123", "role": "receptionist"})
    cashier_account = client.post("/api/users", headers=admin_headers, json={"username": "cashier.a", "password": "Cashier-Password-123", "role": "cashier"})
    manager_account = client.post("/api/users", headers=admin_headers, json={"username": "manager.a", "password": "Manager-Password-123", "role": "manager"})
    assert receptionist_account.status_code == cashier_account.status_code == manager_account.status_code == 201

    def login(username, password):
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    barber_headers = login("barber.a", "Barber-Password-123")
    receptionist_headers = login("reception.a", "Reception-Password-123")
    cashier_headers = login("cashier.a", "Cashier-Password-123")
    manager_headers = login("manager.a", "Manager-Password-123")

    barber_rows = client.get("/api/appointments", headers=barber_headers)
    assert barber_rows.status_code == 200
    assert {x["barber_id"] for x in barber_rows.json()} == {barber_a["id"]}
    assert client.get("/api/customers", headers=barber_headers).status_code == 403
    assert client.get("/api/finance/summary", headers=barber_headers).status_code == 403
    barber_dashboard = client.get("/api/dashboard", headers=barber_headers).json()
    assert "monthly_income" not in barber_dashboard["metrics"]
    assert all(x["barber_id"] == barber_a["id"] for x in barber_dashboard["upcoming"] + barber_dashboard["recent"])
    other_booking_id = book_b.json()["appointment"]["id"]
    assert client.patch(f"/api/appointments/{other_booking_id}", headers=barber_headers, json={"status": "completed"}).status_code == 403
    own_booking_id = book_a.json()["appointment"]["id"]
    assert client.patch(f"/api/appointments/{own_booking_id}", headers=barber_headers, json={"status": "cancelled"}).status_code == 403
    assert client.patch(f"/api/appointments/{own_booking_id}", headers=barber_headers, json={"barber_id": barber_b["id"]}).status_code == 403
    assert client.patch(f"/api/appointments/{own_booking_id}", headers=barber_headers, json={"status": "completed"}).status_code == 409

    assert client.get("/api/appointments", headers=receptionist_headers).status_code == 200
    assert client.get("/api/users", headers=receptionist_headers).status_code == 403
    assert client.post("/api/finance/transactions", headers=receptionist_headers, json={"kind":"expense","category":"supplies","amount":10,"transaction_date":app_module.now_local().date().isoformat()}).status_code == 403
    assert client.get("/api/appointments", headers=cashier_headers).status_code == 200
    assert client.get("/api/finance/summary", headers=cashier_headers).status_code == 200
    assert client.post("/api/appointments", headers=cashier_headers, json={}).status_code == 403
    assert client.post("/api/users", headers=cashier_headers, json={"username":"bad.user","password":"Password-123","role":"manager"}).status_code == 403
    assert client.get("/api/settings", headers=manager_headers).status_code == 200
    assert client.put("/api/settings", headers=manager_headers, json={"settings":{"business_name":"Dreem Manager Updated"}}).status_code == 200
    assert client.get("/api/users", headers=manager_headers).status_code == 403
    assert client.get("/api/backup", headers=manager_headers).status_code == 403
    assert client.post("/api/appointments", headers=manager_headers, json={}).status_code == 422


def test_barber_shifts_time_off_and_schedule_validation(client):
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    day = future_day(app_module, 4)
    import datetime as dt
    weekday = dt.date.fromisoformat(day).weekday()

    # Explicit all-days-off schedule blocks appointments instead of falling back to salon hours.
    all_off = [{"weekday": i, "start_time": "09:00", "end_time": "17:00", "active": False} for i in range(7)]
    saved = client.put(f"/api/barbers/{barber['id']}/shifts", headers=headers, json=all_off)
    assert saved.status_code == 200, saved.text
    blocked = client.post("/api/public/appointments", json=booking_payload(client, day, barber["id"]))
    assert blocked.status_code == 409

    # One valid weekly shift allows a booking inside the shift only.
    shifts = [{"weekday": i, "start_time": "09:00", "end_time": "17:00", "active": i == weekday} for i in range(7)]
    saved = client.put(f"/api/barbers/{barber['id']}/shifts", headers=headers, json=shifts)
    assert saved.status_code == 200, saved.text
    invalid = client.post("/api/public/appointments", json=booking_payload(client, day, barber["id"], "0599000301", "18:00"))
    assert invalid.status_code == 409
    good = client.post("/api/public/appointments", json=booking_payload(client, day, barber["id"], "0599000302", "10:00"))
    assert good.status_code == 201, good.text

    overlap = client.put(f"/api/barbers/{barber['id']}/shifts", headers=headers, json=[
        {"weekday": weekday, "start_time": "09:00", "end_time": "12:00", "active": True},
        {"weekday": weekday, "start_time": "11:00", "end_time": "15:00", "active": True},
    ])
    assert overlap.status_code == 422

    # An absence overlapping an existing booking is rejected; after adding an absence,
    # new bookings inside it are rejected as well.
    existing = good.json()["appointment"]
    absence_conflict = client.post(f"/api/barbers/{barber['id']}/time-off", headers=headers, json={"start_at": existing["start_at"], "end_at": existing["end_at"], "reason": "test"})
    assert absence_conflict.status_code == 409
    absence_day = future_day(app_module, 5)
    absence_start = f"{absence_day}T10:00"
    absence_end = f"{absence_day}T12:00"
    created = client.post(f"/api/barbers/{barber['id']}/time-off", headers=headers, json={"start_at": absence_start, "end_at": absence_end, "reason": "إجازة"})
    assert created.status_code == 201, created.text
    off_day = dt.date.fromisoformat(absence_day).weekday()
    if off_day != weekday:
        weekly = [{"weekday": i, "start_time": "09:00", "end_time": "17:00", "active": i in {weekday, off_day}} for i in range(7)]
        assert client.put(f"/api/barbers/{barber['id']}/shifts", headers=headers, json=weekly).status_code == 200
    denied = client.post("/api/public/appointments", json=booking_payload(client, absence_day, barber["id"], "0599000303", "10:30"))
    assert denied.status_code == 409


def test_rounded_money_and_date_validation(client):
    headers, _ = create_admin(client)
    invalid_small = client.post("/api/finance/transactions", headers=headers, json={"kind":"income","category":"test","amount":0.001,"transaction_date":"2026-11-04"})
    assert invalid_small.status_code == 422
    invalid_date = client.post("/api/finance/transactions", headers=headers, json={"kind":"income","category":"test","amount":1,"transaction_date":"2026-02-30"})
    assert invalid_date.status_code == 422
    good = client.post("/api/finance/transactions", headers=headers, json={"kind":"income","category":"test","amount":1.005,"transaction_date":"2026-11-04"})
    assert good.status_code == 201, good.text
    assert good.json()["transaction"]["amount"] == pytest.approx(1.01)


def test_upgrade_migrates_existing_122_database_without_data_loss(client, tmp_path, monkeypatch):
    from backend.app import main as app_module

    legacy_path = tmp_path / "legacy-1.2.2.db"
    con = sqlite3.connect(legacy_path)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE services (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',duration_minutes INTEGER NOT NULL DEFAULT 30,price REAL NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE barbers (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',specialty TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT NOT NULL UNIQUE,email TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE appointments (id INTEGER PRIMARY KEY AUTOINCREMENT,customer_id INTEGER NOT NULL REFERENCES customers(id),service_id INTEGER NOT NULL REFERENCES services(id),barber_id INTEGER REFERENCES barbers(id),start_at TEXT NOT NULL,end_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'confirmed',price REAL NOT NULL DEFAULT 0,payment_status TEXT NOT NULL DEFAULT 'unpaid',notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,category TEXT NOT NULL,amount REAL NOT NULL,transaction_date TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',appointment_id INTEGER REFERENCES appointments(id),created_at TEXT NOT NULL);
        CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
    """)
    con.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", ("legacy.owner", app_module.hash_password("Legacy-Password-123"), "2026-10-01T10:00:00"))
    con.execute("INSERT INTO services(name,duration_minutes,price,created_at) VALUES(?,?,?,?)", ("Legacy Cut", 30, 35.0, "2026-10-01T10:00:00"))
    con.execute("INSERT INTO barbers(name,created_at) VALUES(?,?)", ("Legacy Barber", "2026-10-01T10:00:00"))
    con.execute("INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)", ("Legacy Customer", "0599000900", "2026-10-01T10:00:00"))
    con.execute("INSERT INTO appointments(customer_id,service_id,barber_id,start_at,end_at,status,price,notes,created_at,updated_at) VALUES(1,1,1,'2026-11-10T10:00','2026-11-10T10:30','confirmed',35,'keep me','2026-10-01T10:00','2026-10-01T10:00')")
    con.execute("INSERT INTO transactions(kind,category,amount,transaction_date,note,appointment_id,created_at) VALUES('income','Legacy Cut',35,'2026-11-10','keep ledger',1,'2026-11-10T10:30')")
    con.commit()
    con.close()

    monkeypatch.setattr(app_module, "DB_PATH", legacy_path)
    app_module.init_db()
    with sqlite3.connect(legacy_path) as migrated:
        users = {row[1] for row in migrated.execute("PRAGMA table_info(users)")}
        appointments = {row[1] for row in migrated.execute("PRAGMA table_info(appointments)")}
        transactions = {row[1] for row in migrated.execute("PRAGMA table_info(transactions)")}
        assert {"role", "active", "barber_id"}.issubset(users)
        assert "refund_status" in appointments
        assert "payment_method" in transactions
        assert migrated.execute("SELECT username,role,active FROM users WHERE id=1").fetchone() == ("legacy.owner", "admin", 1)
        assert migrated.execute("SELECT notes FROM appointments WHERE id=1").fetchone()[0] == "keep me"
        assert migrated.execute("SELECT note FROM transactions WHERE id=1").fetchone()[0] == "keep ledger"
        assert migrated.execute("SELECT COUNT(*) FROM barber_shifts").fetchone()[0] == 0


def test_database_backup_is_admin_only_and_valid_sqlite(client):
    headers, _ = create_admin(client)
    backup = client.get("/api/backup", headers=headers)
    assert backup.status_code == 200, backup.text
    assert backup.headers.get("content-type", "").startswith("application/vnd.sqlite3")
    assert backup.content.startswith(b"SQLite format 3\x00")
    receptionist = client.post("/api/users", headers=headers, json={"username": "frontdesk", "password": "Reception-123", "role": "receptionist"})
    assert receptionist.status_code == 201, receptionist.text
    login = client.post("/api/auth/login", json={"username": "frontdesk", "password": "Reception-123"})
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/backup", headers=staff_headers).status_code == 403


def test_future_completion_and_reopening_completed_appointments_are_rejected(client):
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    day = future_day(app_module, 4)
    booking = client.post(
        "/api/public/appointments",
        json=booking_payload(client, day, barber["id"], "0599000401", "10:00"),
    )
    assert booking.status_code == 201, booking.text
    appointment_id = booking.json()["appointment"]["id"]

    future_complete = client.patch(
        f"/api/appointments/{appointment_id}", headers=headers, json={"status": "completed"}
    )
    assert future_complete.status_code == 409, future_complete.text
    cancelled_to_complete = client.patch(
        f"/api/appointments/{appointment_id}", headers=headers, json={"status": "cancelled"}
    )
    assert cancelled_to_complete.status_code == 200, cancelled_to_complete.text
    direct_complete = client.patch(
        f"/api/appointments/{appointment_id}", headers=headers, json={"status": "completed"}
    )
    assert direct_complete.status_code == 409, direct_complete.text

    # Simulate a legacy/manual completion record and ensure it cannot be silently reopened.
    with app_module.db() as con:
        con.execute("UPDATE appointments SET status='completed' WHERE id=?", (appointment_id,))
    reopened = client.patch(
        f"/api/appointments/{appointment_id}", headers=headers, json={"status": "confirmed"}
    )
    assert reopened.status_code == 409, reopened.text


def test_schedule_change_cannot_invalidate_future_bookings(client):
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    day = future_day(app_module, 5)
    booking = client.post(
        "/api/public/appointments",
        json=booking_payload(client, day, barber["id"], "0599000402", "10:00"),
    )
    assert booking.status_code == 201, booking.text

    import datetime as dt
    weekday = dt.date.fromisoformat(day).weekday()
    closed_schedule = [
        {"weekday": i, "start_time": "09:00", "end_time": "17:00", "active": False}
        for i in range(7)
    ]
    rejected = client.put(f"/api/barbers/{barber['id']}/shifts", headers=headers, json=closed_schedule)
    assert rejected.status_code == 409, rejected.text

    # The rejected schedule update must roll back atomically and retain the old inherited-hours state.
    shifts = client.get(f"/api/barbers/{barber['id']}/shifts", headers=headers)
    assert shifts.status_code == 200
    assert shifts.json() == []
    assert booking.json()["appointment"]["start_at"].startswith(day)


def test_concurrent_requests_cannot_reserve_the_same_barber_slot(client):
    from concurrent.futures import ThreadPoolExecutor
    from backend.app import main as app_module

    headers, _ = create_admin(client)
    barber = create_barber(client, headers)
    day = future_day(app_module, 6)
    service_id = client.get("/api/public/services").json()[0]["id"]

    payloads = [
        {
            "customer_name": f"Concurrent Customer {i}",
            "customer_phone": f"05990004{i:02d}",
            "service_id": service_id,
            "barber_id": barber["id"],
            "start_at": f"{day}T10:00",
            "notes": "parallel slot test",
        }
        for i in (3, 4)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda item: client.post("/api/public/appointments", json=item), payloads))
    assert sorted(response.status_code for response in responses) == [201, 409]
    rows = client.get("/api/appointments", headers=headers).json()
    assert sum(1 for row in rows if row["barber_id"] == barber["id"] and row["start_at"] == f"{day}T10:00") == 1


def test_admin_can_create_recovery_admin_and_last_admin_cannot_be_disabled(client):
    headers, _ = create_admin(client)
    recovery = client.post(
        "/api/users",
        headers=headers,
        json={"username": "owner.backup", "password": "Backup-Admin-123", "role": "admin"},
    )
    assert recovery.status_code == 201, recovery.text
    recovery_id = recovery.json()["user"]["id"]
    login = client.post("/api/auth/login", json={"username": "owner.backup", "password": "Backup-Admin-123"})
    assert login.status_code == 200, login.text
    recovery_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/users", headers=recovery_headers).status_code == 200

    # A second active administrator can be disabled, but the final administrator cannot.
    disabled = client.patch(f"/api/users/{recovery_id}", headers=headers, json={"active": False})
    assert disabled.status_code == 200, disabled.text
    last_admin = client.get("/api/users", headers=headers).json()
    owner = next(item for item in last_admin if item["username"] == "owner.test")
    rejected = client.patch(f"/api/users/{owner['id']}", headers=headers, json={"active": False})
    assert rejected.status_code == 409, rejected.text
