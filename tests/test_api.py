from __future__ import annotations

from datetime import timedelta

def create_admin(client):
    response = client.post(
        "/api/setup",
        json={"username": "owner.test", "password": "Strong-Password-123", "business_name": "Dreem Test"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token

def test_health_setup_login_and_password_rotation(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "1.2.1"
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

def test_public_booking_conflict_payment_and_csv_safety(client):
    from backend.app import main as app_module
    headers, _ = create_admin(client)
    barber_response = client.post(
        "/api/barbers",
        headers=headers,
        json={"name": "Test Barber", "phone": "0599000123", "specialty": "قص شعر", "active": True},
    )
    assert barber_response.status_code == 201, barber_response.text
    barber = barber_response.json().get("barber", barber_response.json())
    service = client.get("/api/public/services").json()[0]
    booking_day = (app_module.now_local().date() + timedelta(days=3)).isoformat()
    booking_data = {
        "customer_name": "=2+2",
        "customer_phone": "0599000999",
        "service_id": service["id"],
        "barber_id": barber["id"],
        "start_at": f"{booking_day}T10:00",
        "notes": "API test",
    }
    booked = client.post("/api/public/appointments", json=booking_data)
    assert booked.status_code == 201, booked.text
    appointment_id = booked.json()["appointment"]["id"]

    conflict = client.post("/api/public/appointments", json=booking_data)
    assert conflict.status_code == 409, conflict.text
    paid = client.post(f"/api/appointments/{appointment_id}/pay", headers=headers)
    assert paid.status_code == 200, paid.text
    assert client.post(f"/api/appointments/{appointment_id}/pay", headers=headers).status_code == 409

    assert client.get("/api/finance/summary", headers=headers).status_code == 200
    export = client.get("/api/export/appointments.csv", headers=headers)
    assert export.status_code == 200
    assert "'=2+2" in export.text

def test_invalid_date_filter_is_rejected(client):
    headers, _ = create_admin(client)
    response = client.get("/api/appointments?date=not-a-date", headers=headers)
    assert response.status_code == 422
