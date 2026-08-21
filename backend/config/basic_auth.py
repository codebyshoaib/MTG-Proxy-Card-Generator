"""Optional HTTP Basic Auth for the Milestone 1 demo.

There is no real user auth yet. An open URL with GEMINI_API_KEY behind it is a bill anyone can
burn. Set DEMO_BASIC_AUTH_USER and DEMO_BASIC_AUTH_PASSWORD to gate the whole app. Leave both
unset locally so tests and `runserver` stay untouched. /api/health stays open for Render checks.
"""

import base64
import hmac
import os


class DemoBasicAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.user = os.environ.get("DEMO_BASIC_AUTH_USER", "").strip()
        self.password = os.environ.get("DEMO_BASIC_AUTH_PASSWORD", "").strip()

    def __call__(self, request):
        if not self.user or not self.password:
            return self.get_response(request)
        if request.path.rstrip("/") == "/api/health":
            return self.get_response(request)
        if self._ok(request.META.get("HTTP_AUTHORIZATION", "")):
            return self.get_response(request)
        from django.http import HttpResponse

        response = HttpResponse("Authentication required.", status=401)
        response["WWW-Authenticate"] = 'Basic realm="MTG demo"'
        return response

    def _ok(self, header: str) -> bool:
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            user, _, password = decoded.partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        return hmac.compare_digest(user, self.user) and hmac.compare_digest(
            password, self.password
        )
