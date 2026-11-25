import sys
import os

# Add the running-tracker directory to Python path so 'app' can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# === Fix for Cyrillic mojibake on Windows ===
# httpx sends Content-Type without charset; WSGI defaults to latin-1.
# Patch before any TestClient imports to force UTF-8 in WSGI environ.
import httpx._transports.wsgi as wsgi_mod

_original_wsgi_handle_request = wsgi_mod.WSGITransport.handle_request


def _patched_wsgi_handle_request(self, request):
    ct = request.headers.get("content-type", "")
    if "charset=" not in ct.lower():
        request.headers["content-type"] = f"{ct}; charset=utf-8"
    return _original_wsgi_handle_request(self, request)


wsgi_mod.WSGITransport.handle_request = _patched_wsgi_handle_request
