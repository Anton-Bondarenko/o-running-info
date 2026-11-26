"""Entry point for running the tracker server."""
import os
import uvicorn

# Load .env safely — use dotenv_values which handles all encodings
try:
    from dotenv import dotenv_values
    _env_path = '/app/.env' if os.path.exists('/app/.env') else '.env'
    vals = dotenv_values(_env_path)
    if vals:
        for k, v in vals.items():
            if v is not None:
                os.environ.setdefault(k, v)
except ImportError:
    pass  # dotenv not installed, use defaults

if __name__ == "__main__":
    host = os.environ.get("SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("SERVER_PORT", "8000"))
    workers = int(os.environ.get("WORKERS", "1"))

    print(f"[*] Starting server on {host}:{port} ({workers} worker{'s' if workers > 1 else ''})")
    uvicorn.run("app.main:app", host=host, port=port, workers=workers)
