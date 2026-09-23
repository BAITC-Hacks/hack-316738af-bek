from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app.access import ACCESS_COOKIE, ACCESS_TTL, issue_access, valid_access
from backend.app.main import create_app


def test_signed_access_expiration_rotation_and_tamper():
    cookie = issue_access("test-secret", now=1800000000)
    assert valid_access(cookie, "test-secret", now=1800000001)
    assert not valid_access(cookie, "changed-secret", now=1800000001)
    assert not valid_access(cookie, "test-secret", now=1800000000 + ACCESS_TTL)
    assert not valid_access(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"), "test-secret", now=1800000001)
    assert not valid_access("bad", "test-secret")


def test_browser_login_does_not_expose_secret_and_preserves_session_isolation(settings):
    app = create_app(replace(settings, access_token="judge-test-secret"))
    with TestClient(app) as client:
        assert client.get("/", follow_redirects=False).headers["location"] == "/access"
        assert "judge-test-secret" not in client.get("/access").text
        assert client.post("/api/analyses").status_code == 404
        assert client.post("/access", data={"code": "wrong"}).status_code == 403
        response = client.post("/access", data={"code": "judge-test-secret"}, follow_redirects=False)
        assert response.status_code == 303
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "judge-test-secret" not in cookie
        first = client.post("/api/analyses")
        assert first.status_code == 201
        other = TestClient(app)
        try:
            other.post("/access", data={"code": "judge-test-secret"})
            other.post("/api/analyses")
            assert other.get(f"/api/analyses/{first.json()['analysis_id']}").status_code == 404
        finally:
            other.close()
        client.cookies.clear()
        client.cookies.set(ACCESS_COOKIE, "forged")
        assert client.post("/api/analyses").status_code == 404


def test_login_origin_rate_limit_and_https_cookie(settings):
    app = create_app(replace(settings, access_token="test-secret", secure_cookie=True))
    with TestClient(app, base_url="https://testserver") as client:
        assert (
            client.post("/access", data={"code": "test-secret"}, headers={"Origin": "https://wrong.test"}).status_code
            == 400
        )
        for _ in range(10):
            assert client.post("/access", data={"code": "wrong"}).status_code == 403
        assert client.post("/access", data={"code": "test-secret"}).status_code == 429
    app = create_app(replace(settings, access_token="test-secret", secure_cookie=True))
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/access", data={"code": "test-secret"}, follow_redirects=False)
        assert "Secure" in response.headers["set-cookie"]
        assert client.post("/api/analyses").status_code == 201
