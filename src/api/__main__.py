"""Run the API for development:  python -m src.api   (127.0.0.1:8000, one process, no reload).

For a public deployment put a reverse proxy with HTTPS in front and set ALLOWED_HOSTS, TRUST_PROXY=1 and API_HSTS=1 (docs/security.md).
"""
import os

import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    uvicorn.run("src.api.app:create_app", factory=True, host=os.environ.get("API_HOST", "127.0.0.1"), port=int(os.environ.get("API_PORT", "8000")),
                server_header=False, log_level="warning")
