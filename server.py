"""배포용 진입점 — FastAPI 앱(api/app/main.py)을 저장소 루트에서 불러온다.

Vercel Services의 api 서비스가 `server:app`으로 로드한다. 로컬에서는
`python -m uvicorn server:app --port 8000` 으로도 실행할 수 있다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (ROOT / "src", ROOT / "api"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.main import app  # noqa: E402,F401
