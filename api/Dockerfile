# Railway용 FastAPI 백엔드 컨테이너
# 빌드: docker build -t site-screener-api -f api/Dockerfile .
# 로컬: docker run -p 8000:8000 -e PORT=8000 site-screener-api
FROM python:3.12-slim

WORKDIR /app

# 의존성 먼저 (캐시 최적화)
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# 코드 + 공개용 데이터 (scripts/export_public.py 산출물 — 중개사 정보 제거본)
COPY src/ /app/src/
COPY api/ /app/api/
COPY config/default.yaml /app/config/default.yaml
COPY data/published/ /app/data/published/
COPY reference/seoul_gu.geojson /app/reference/seoul_gu.geojson
COPY reference/seoul_subway_lines.geojson /app/reference/seoul_subway_lines.geojson
COPY reference/seoul_subway_stations.geojson /app/reference/seoul_subway_stations.geojson

# PYTHONPATH로 naver_crawler 모듈 + app 모듈 접근
ENV PYTHONPATH=/app/src:/app/api
WORKDIR /app/api

# Railway는 PORT 환경변수 제공 (default 8000)
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
