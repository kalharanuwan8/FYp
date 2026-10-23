def test_unauthenticated_user_access(client):
    res = client.get("/api/admin/users")
    assert res.status_code == 401

def test_login(client, admin_user):
    res = client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "password123"
    })
    assert res.status_code == 200
    assert "access_token" in res.json
