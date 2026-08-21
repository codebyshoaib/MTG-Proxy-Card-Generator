"""Demo basic-auth middleware: off unless both env vars are set."""

from django.test import SimpleTestCase, override_settings
from django.test.client import RequestFactory

from config.basic_auth import DemoBasicAuthMiddleware


def _mw(user="", password=""):
    with override_settings():
        pass
    import os

    os.environ.pop("DEMO_BASIC_AUTH_USER", None)
    os.environ.pop("DEMO_BASIC_AUTH_PASSWORD", None)
    if user:
        os.environ["DEMO_BASIC_AUTH_USER"] = user
    if password:
        os.environ["DEMO_BASIC_AUTH_PASSWORD"] = password
    return DemoBasicAuthMiddleware(lambda request: type("R", (), {"status_code": 200})())


class DemoBasicAuthTests(SimpleTestCase):
    def tearDown(self):
        import os

        os.environ.pop("DEMO_BASIC_AUTH_USER", None)
        os.environ.pop("DEMO_BASIC_AUTH_PASSWORD", None)

    def test_off_when_unset(self):
        mw = _mw()
        request = RequestFactory().get("/api/options")
        self.assertEqual(mw(request).status_code, 200)

    def test_health_stays_open(self):
        mw = _mw("demo", "secret")
        request = RequestFactory().get("/api/health")
        self.assertEqual(mw(request).status_code, 200)

    def test_rejects_without_credentials(self):
        mw = _mw("demo", "secret")
        request = RequestFactory().get("/api/options")
        self.assertEqual(mw(request).status_code, 401)

    def test_accepts_valid_basic_auth(self):
        import base64

        mw = _mw("demo", "secret")
        token = base64.b64encode(b"demo:secret").decode()
        request = RequestFactory().get(
            "/api/options", HTTP_AUTHORIZATION=f"Basic {token}"
        )
        self.assertEqual(mw(request).status_code, 200)
