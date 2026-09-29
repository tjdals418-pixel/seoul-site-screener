# 배포 — Vercel 하나로 (웹 + API)

Vercel **Services**(베타)로 Next.js 화면(`web/`)과 FastAPI(`server.py` → `api/app`)를
한 프로젝트·한 도메인에 배포합니다. Hobby(무료) 플랜에서 동작하며, 배포 데이터는 저장소에
포함된 `data/public/articles.json.gz`(중개사 정보 제거본) 하나뿐입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `vercel.json` | 서비스 정의 — `/api/*` → `api` 서비스, 나머지 → `web` 서비스, 리전 `icn1`(서울) |
| `server.py` | FastAPI 진입점 (`server:app`) |
| `pyproject.toml` | API 런타임 의존성 (크롤러 패키지는 `[crawler]` 선택 설치라 번들에 안 들어감) |

## 처음 한 번

1. GitHub에 저장소를 올립니다 (공개 저장소 권장).
2. Vercel → **Add New → Project** → 저장소 선택.
3. Framework(프리셋)를 **Services** 로 지정하고 Root Directory는 비워 둡니다 (저장소 루트).
   베타 기능이라 화면 문구가 조금 다를 수 있습니다.
4. **Environment Variables**
   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_MAPBOX_TOKEN` | Mapbox 공개 토큰 (`pk.`로 시작) |
5. **Deploy**. 완료 후 `https://<프로젝트>.vercel.app/api` 가 `{"status":"ok", ...}` 를
   돌려주면 API까지 정상입니다.
6. Mapbox 계정 → Access tokens → 토큰의 URL 제한에 `https://<프로젝트>.vercel.app` 을
   추가해 두면 토큰을 다른 사이트에서 못 씁니다.

첫 접속이 한동안 없으면 API가 잠들어 있다가 1~3초 늦게 뜰 수 있습니다 (Vercel Functions 특성).

## 데이터 갱신 (PC에서, 원할 때)

```bash
pip install -e ".[crawler]"                # 처음 한 번
python -m playwright install chrome        # 처음 한 번
python -m naver_crawler run                # 수집 ~ 필지 (수 시간 — enrich가 가장 오래 걸림)
python scripts/snapshot.py                 # 호가 변동 비교용 스냅샷 (로컬 보관)
python scripts/export_public.py            # data/public/articles.json.gz 갱신
git add data/public && git commit -m "data: YYYY-MM-DD" && git push
```

push하면 Vercel이 자동으로 다시 배포합니다. `scripts/run_weekly.bat`은 실행 ~ export를
한 번에 돌립니다 (push는 직접).

## Services 빌드가 실패하면 — Vercel 프로젝트 2개로 (코드 수정 없음)

Services는 베타라 설정 검증 규칙이 바뀔 수 있습니다. 첫 배포가 설정 오류로 실패하면:

1. `vercel.json` → `vercel.services.json` 으로 이름 변경 후 push
   (`destination: {service}` 형식은 Services 모드가 아니면 오류라 남겨 둘 수 없음)
2. **API 프로젝트**: 같은 저장소로 새 프로젝트, Root Directory 비움(루트), Framework
   FastAPI — `pyproject.toml` + `server.py`로 자동 인식
3. **웹 프로젝트**: 같은 저장소로 새 프로젝트, Root Directory `web`, 환경변수
   `NEXT_PUBLIC_MAPBOX_TOKEN` + `API_PROXY_TARGET=https://<API 프로젝트>.vercel.app`
   (`next.config.ts`가 `/api/*`를 그 주소로 전달)

그 밖에 API를 상시 켜진 Docker 서버에 두려면 `api/Dockerfile` + `railway.toml`(Railway, 월 약 $5).
