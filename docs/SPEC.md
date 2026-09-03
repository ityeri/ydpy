# ydpy — 프로젝트 사양서 v1.1

> yt-dlp 2026.08.19 소스 심층 분석 기반 (venv: /config/workspace/.venv-yt)
> 작성: 2026-09-03 / 결정 반영: v1.1 (아래 §12)

---

## 0. 요약

yt-dlp의 유튜브 전용 우회 지식(멀티 클라이언트 innertube, n/sig JS 챌린지, PO 토큰 정책)을 **기능 레벨에서 계승**하되, 코드는 완전 신규 작성(clean-room). CLI 성격(플레이리스트 자동 확장, 포맷 병합, 파일명 규칙, 터미널 출력)은 전부 제거하고, **"스트림 조회 → 단일 스트림 다운로드"**라는 저수준·예측 가능한 라이브러리 API만 남긴다. 동기/비동기 이중 지원(yspy 패턴), sink 추상화(파일/버퍼/스트림).

### 2026년 현재 유튜브 "봇 우회"의 실체 (yt-dlp 분석 결과)

| 난관 | 내용 | yt-dlp 해법 (2026.08) |
|---|---|---|
| 클라이언트 다양화 | 클라이언트별로 포맷/정책/제약이 다름 (web_creator=로그인 필수, tv=DRM 실험, web_safari HLS=신뢰 세션 한정) | `INNERTUBE_CLIENTS` 테이블 + 우선순위/정책, 여러 클라이언트 순차 시도 후 streamingData 병합 |
| JS 챌린지 (n/sig) | 스트림 URL의 `n` 파라미터를 플레이어 JS 함수로 변환해야 CDN 스로틀 해제. 2025~26년부터 난독화 고도화 → 순수 파이썬 jsinterp 포기 | 실제 JS 엔진에서 플레이어 JS를 실행하는 provider 시스템 (`youtube/jsc/`). 챌린지 값 = URL의 n값 자체. 일괄(bulk) 해결 후 `(player, challenge) → result` 캐시. 런타임: node(선호도 900) > quickjs-ng(850) > deno(기본 내장) 등 |
| PO 토큰 (pot) | googlevideo 스트림 URL에 pot 파라미터 요구. 클라이언트×프로토콜별 정책 | 토큰 **발급은 내장 안 함** — 외부 제공자(bgutil 등) + 문맥 3종(player/gvs/subs) + 정책 테이블(`youtube/pot/`) + 캐시 |

---

## 1. 목표 / 비목표

### 구현 목표
1. 유튜브 **영상 1개** 입력 → 플레이어 API 응답 획득 → **스트림(Format) 목록** 반환
2. 각 스트림에 대한 **단순 다운로드** (저수준, 병합 없음, 변환 없음)
3. n/sig JS 챌린지 해석 (clean-room solver + JS 런타임) + 결과 캐시
4. PO 토큰 정책 판정 + **외부 제공자 연동** + 캐시
5. 동기/비동기 이중 API (yspy 패턴)
6. sink 추상화: 로컬 경로 / file-like / 메모리 버퍼 / 커스텀
7. 속도: 스로틀 회피 + HTTP 고속화 + 스로틀 감지 폴백

### 비목표
- **플레이리스트/채널/검색** — 영상 URL 1개만 (`list=` 무시)
- **포맷 병합, ffmpeg, 파일명 생성 규칙, 컨테이너 변환** — 원시 스트림까지만
- **CLI** — 옵션은 전부 명시적 파라미터(frozen dataclass)
- **video availability / 상세 메타데이터** — yspy 도메인
- **로그인/쿠키 기반 프리미엄·연령 제한** (v1) — 익명 기준. 쿠키 주입 지점만 설계에 남김
- **PO 토큰 자체 발급(WebPO 챌린지 클라이언트)** — 이동 표적, 별도 관리 주체. ydpy는 외부 발급 연동만 (결정됨)
- **YouTube 외 사이트**

---

## 2. yt-dlp 분석 — 계승 지식 요약

### 2.1 추출 파이프라인
```
URL → video_id (11자 검증)
  → watch 페이지 HTML 1회 GET (ytcfg: PLAYER_JS_URL / visitorData / signatureTimestamp / 초기 playerResponse)
  → 클라이언트 목록: 익명+JS런타임=(visionos, web) / 익명+무런타임=(visionos,)  [2026.08 yt-dlp 기본]
  → 클라이언트별 innertube POST /youtubei/v1/player
       body: context.client{clientName, clientVersion, UA...} + visitorData
       query: api_key, (signatureTimestamp), (player pot → serviceIntegrityDimensions.poToken)
  → streamingData(formats + adaptiveFormats + hls/dashManifestUrl) 수집
  → [1차 패스] 챌린지 수집: URL parse_qs['n'], signatureCipher 's', 매니페스트 URL n
  → [일괄 해결] director: 런타임 선택 → 플레이어 JS 실행 → 결과 검증(결과==입력 or 입력으로 끝나면 무효)
       → (player, challenge)→result 캐시
  → [2차 패스] 포맷 생성: DRM 드랍, 손상 의심(approxDurationMs < duration/2) 드랍/감점, itag17 보정,
       missing_pot(required+토큰 없음) 드랍(경고), n 치환
```

### 2.2 PO 토큰 정책
- 문맥 3종: player / gvs / subs. 2026.08 발췌: web HTTPS·DASH **required**(프리미엄 면제, player 토큰으로도 면제 안 됨), HLS recommended / android HTTPS·DASH required(**player 토큰 있으면 면제**) / web_music·web_creator GVS required
- 익명 다운로드는 GVS pot 없으면 상당수 포맷 403 → 발급 연동이 실질 필수
- yt-dlp pot/ 구조: director(정책 판정·제공자 선택·오류 처리) → provider(외부) → cache(memory+disk cachespec, 만료 포함)

### 2.3 JS 챌린지 (jsc)
- JsChallengeProvider: `_SUPPORTED_TYPES(N/SIG)`, `is_available()`, `bulk_solve()`(부분 성공 허용)
- director: preference 합산 정렬 → 차례로 시도 → 응답 검증 → 미해결 건 다음 제공자
- 런타임 제공자: node(900) / quickjs-ng(850) / deno / bun / ejs(원격 컴포넌트). quickjs는 단일 CLI 바이너리(`quickjs`/`quickjs-ng`, 2025-04-26/0.12+ 권장)를 subprocess로 호출 — **stdin 미지원이라 임시파일 사용**
- 플레이어 JS 캐시 (player_id→code, 메모리+디스크), n/sig 결과 캐시 키 `(youtube-n, player_js_key, challenge)`

### 2.4 HTTP 다운로더 (전체 분석)
- 단일 연결 순차 + Range 재개. 병렬 청크 없음
- `Accept-Encoding: identity` — Content-Length 확정
- 가변 블록: 측정 속도 기반, 하한 bytes/2 ~ 상한 bytes*2, **최대 4MB**
- Content-Range 검증(서버 Range 무시 → 전체 재다운로드), 416 → ±100B 완료 판정
- **스로틀 감지**: 임계(예: 500KB/s) 미만 3초 → ThrottledDownload → 클라이언트/포맷 재시도
- 전송 오류 시 파일 크기 기반 재개

---

## 3. 패키지 구조 (uv + src-layout, ityeri 컨벤션)

```
src/ydpy/
  __init__.py            # 공개 API만 (__all__)
  exceptions.py          # 예외 계층 (1줄 클래스)
  request/               # innertube/HTTP (yspy request 패턴)
    __init__.py
    utils.py             # RequestData dataclass + optional_async_client + 상수(api_key, host)
    player.py            # player API POST (클라이언트 컨텍스트 빌드, get/aget 쌍)
    webpage.py           # watch 페이지 GET + ytcfg 추출 (get/aget 쌍)
  client.py              # 클라이언트 테이블 (frozen) + CLIENTS 기본 (visionos, web) + 정책
  jsplayer.py            # 플레이어 JS: URL 결정, fetch, 캐시, sts 추출
  challenge/             # JS 챌린지 (clean-room)
    __init__.py
    base.py              # JsChallengeRequest/Response, N/Sig 타입 (frozen)
    runtime.py           # Runtime 프로토콜 + QuickJsRuntime/NodeRuntime/DenoRuntime (+우선순위)
    solver.py            # solver 스크립트 — 순수 JS, 자체 작성 (난독화 동적 탐색)
    director.py          # 런타임 선택, 일괄 해결, 검증, 캐시
  pot/                   # PO 토큰
    __init__.py
    base.py              # PoTokenRequest/Response, 정책 enum/테이블
    provider.py          # PoTokenProvider 프로토콜 (외부 연동 전용)
    director.py          # 정책 판정 → 발급/캐시(만료)
  cache.py               # 메모리 LRU + 선택적 디스크
  streams.py             # Format 모델 + 도메인 enum + from_json
  extract.py             # 오케스트레이션: 영상 1개 → Format 목록 (순수 파이프라인)
  downloader.py          # sink + 다운로드 루프 (sync/async)
  video.py               # Video 사용자 엔티티
```

### 핵심 타입 (전부 @dataclass(frozen=True))
```python
@dataclass(frozen=True)
class Client:
    name: str                       # 'visionos' | 'web'
    client_name: str                # innertube clientName
    client_version: str
    user_agent: str | None = None
    priority: int
    require_js_player: bool         # visionos=False, web=True
    gvs_pot_policy: GvsPolicy

@dataclass(frozen=True)
class Format:
    itag: int
    client: str
    url: str                        # n 치환 완료, pot 미첨부
    protocol: StreamingProtocol     # HTTPS/DASH/HLS
    mime_type: str | None
    container: Container | None     # 도메인 enum (streams.py 내 배치)
    video_codec: VideoCodec | None  # enum.property로 부가정보
    audio_codec: AudioCodec | None
    width/height/fps: int | None
    bitrate: int | None
    filesize: int | None
    approx_duration_ms: int | None
    has_drm: bool
    quality_label: str | None
    requires_pot: bool
    is_damaged: bool = False
    @staticmethod
    def from_json(raw: dict, ...) -> 'Format': ...    # get_by_path 기반
    def with_n(self, solved: str) -> 'Format': ...    # dataclasses.replace 불변 변환
    def with_pot(self, token: str) -> 'Format': ...

@dataclass(frozen=True)
class VideoData:
    id: str
    title: str | None               # 최소 식별 정보만 (yspy 침범 금지)
    duration_ms: int | None
    formats: tuple[Format, ...]

@dataclass(frozen=True)
class DownloadOptions:
    chunk_size: int = 0
    retries: int = 5
    timeout: float = 30.0
    throttled_rate_limit: int = 500_000
    http2: bool = False
    parallel_ranges: int = 1        # v1.1+
    proxy: str | None = None
    verify_tls: bool = True
    progress: Callable[[DownloadProgress], None] | None = None
```

### sink 프로토콜
```python
class Sink(Protocol):
    def write(self, data: bytes) -> None: ...
```
- 팩토리: `file_sink(path)` / `buffer_sink()` → BytesIO(사용자 소유) / `stream_sink(write_fn)`
- v1.1 병렬 청크 대비: seek/tell 지원 sink = 병렬 허용, append-only = 순차 전용

---

## 4. 공개 API (동기/비동기 이중)

```python
video = ydpy.Video("https://www.youtube.com/watch?v=...")   # 파싱만 (네트워크 없음)

data = video.fetch()          # or: await video.afetch()   → 불변 VideoData
data.formats                  # tuple[Format, ...]

result = data.formats[0].download(path_or_sink, options=...)    # sync
result = await data.formats[0].adownload(path_or_sink, ...)     # async
```
- 동기 = 깨끗한 이름, 비동기 = `a` 접두사 (yspy get/aget 계열)
- request 레이어만 httpx Client/AsyncClient 이중(함수당 ~10줄). 파싱·챌린지·정책 = 순수 동기 코어. 비동기에서 subprocess/to_thread

---

## 5. 다운로드 속도 개선

| # | 기법 | 효과 | v1 |
|---|---|---|---|
| 1 | n/sig 챌린지 정확 해석 | 미해결 = CDN 스로틀(수십~수백 KB/s). "속도 개선"의 90% | ✅ |
| 2 | 클라이언트 선택 전략 (visionos → web) | 무런타임 환경에서도 동작 보장 | ✅ |
| 3 | Accept-Encoding: identity | Content-Length 확정, gzip CPU 제거 | ✅ |
| 4 | 가변 블록 (속도 기반, 상한 4MB) | yt-dlp 검증 알고리즘 | ✅ |
| 5 | 스로틀 감지 폴백 (임계 미만 3초) | 클라이언트/포맷 자동 재시도 | ✅ |
| 6 | 연결 재사용 + 선택적 HTTP/2 | 다중 요청 비용 절감 | ✅ |
| 7 | Range 재개 재시도 | 전송 오류 시 부분 진행 보존 | ✅ |
| 8 | 병렬 Range 청크 | 단일 연결 풀스피드면 이득 0 + 복잡도 → v1.1 | 🔜 |
| 9 | Range 무시 서버 대응 (Content-Range 검증) | | ✅ |

**v1 = 단일 연결 최대 속도 + 스로틀 자동 회피.** 병렬 청크는 v1.1 선택 기능.

---

## 6. JS 챌린지 (challenge/) — v1 (결정 반영)

- **solver 스크립트: clean-room 자체 작성** (결정됨). yt-dlp 코드/스크립트 복사 금지. 회귀 시 외부 컴포넌트 훅(스크립트 경로/명령 주입)만 문서화해 남김
- solver(순수 JS) 역할: 플레이어 JS를 런타임에서 평가 → n/sig 함수 **동적 탐색**(정적 regex 아님 — 난독화 대응) → 챌린지 값 일괄 변환 → stdout JSON
- **Runtime 프로토콜** (`runtime.py`): `is_available()` / `run(script: str) -> str` (stdin 또는 임시파일)
  - 우선순위(자동 감지 + 사용자 지정 경로):
    1. **quickjs-ng/quickjs CLI** — 단일 바이너리(~2MB)로 가장 가벼움, stdin 미지원 → 임시파일 방식 (yt-dlp 850점 사용 실증)
    2. **node** — yt-dlp 최상위 선호(900)
    3. **deno** — 안전 플래그(--no-remote 등) 기본 내장
  - **인프로세스 임베드(pip quickjs)**: 후보 1순위였으나 PyPI sdist가 C 빌드 필요(Python.h) + cp314 wheel 부재 확인(2026-09-03 실측) → **선택적 최적화로만**: M3 전 스파이크에서 실 player JS 대상 성능/호환 검증 후 채택 결정 (프로세스 오버헤드 제거 목적, 필수 아님)
- 검증: 결과==입력 or 입력으로 끝나면 무효(JS 예외). 가능 시 googlevideo `Range: bytes=0-0` 프로브(선택)
- 캐시: (player_url→code) 메모리+디스크 / (player_url, challenge)→result LRU+디스크. 플레이어 버전 키 구분
- 런타임 0개 환경: visionos 클라이언트만 사용 + 명확한 경고 (yt-dlp JSLESS 동일 전략)

---

## 7. PO 토큰 (pot/) — v1 (결정 반영)

- **외부 제공자 연동 전용** (결정됨). 정책 판정 + `PoTokenProvider` 프로토콜 + 캐시(만료 포함)만 내장
- 내장 `PoTokenProvider` 예시: bgutil-ytdlp-pot-provider HTTP 연동 래퍼 (문서 + 예제 코드)
- required 포맷에 제공자/토큰 없음 → 해당 포맷 제외(경고, 'MISSING POT' 표기) + 무pot 포맷/클라이언트 폴백 (yt-dlp missing_pot 정책 동일)
- WebPO 자체 발급 구현 = **비목표** (별도 관리 주체)

---

## 8. 에러 계층 (exceptions.py)
```
YdpyException(Exception)
├── InvalidVideoIdentifierException(ValueError)   # yspy 합의 명명, 메시지에 입력값
├── RequestException              # 네트워크/HTTP
├── ExtractionException           # player 응답 파싱/무효
├── ChallengeException            # 런타임 없음/해결 실패
├── PolicyException               # pot required + 제공자 없음 등
└── DownloadException             # 수신/기록 실패 (ThrottledDownload 포함)
```

---

## 9. 코드 컨벤션 (ityeri)
- uv + src-layout, 의존성 최소: httpx, yarl (+선택 h2, +선택 quickjs 임베드)
- frozen dataclass + from_json, get_by_path + DataParsingException 계열 래핑
- enum = 도메인 파일 내(streams.py), 매핑 dict = enum property
- PEP 604 타입힌트 필수, 커밋 `prefix: 영어 서술문`, 영어 주석/로그+유머, 사용자 문자열 한국어
- 부작용 최소: 불변 객체 + dataclasses.replace, 네트워크는 명시적 호출로만

---

## 10. 검증 전략
- 라이브 매트릭스: 일반/Shorts/종료 라이브 VOD × (visionos, web) — 포맷 존재·200·속도
- 픽스처: player 응답 JSON 저장, 챌린지 결과 재현성
- 벤치: yt-dlp 대비 속도 (동일 영상/포맷)
- 단위: 클라이언트 폴백, pot 정책 표, sink별 기록, Range 재개/416, 블록 적응

---

## 11. 마일스톤
| 단계 | 내용 | 완료 기준 (라이브) |
|---|---|---|
| M0 | **스파이크: JS 런타임 × 실 player JS** (quickjs-ng/node/deno/pip quickjs 평가) | 런타임 1개 이상 n-해석 성공 |
| M1 | request 레이어 + watch/ytcfg + visionos·web player API | streamingData 확보 |
| M2 | Format 모델 + 클라이언트 폴백 + 순차 다운로더 | 무챌린지 포맷 다운로드 성공 |
| M3 | clean-room solver + 런타임 + 캐시 | web 고해상도 풀스피드 |
| M4 | POT 정책/provider/캐시 + bgutil 연동 문서 | 403 없이 포맷 확보 |
| M5 | 스로틀 폴백, 진행 콜백, async 검증, 벤치, 문서 | 동기/비동기 영상 3종 통과 |
| v1.1 | 병렬 Range 청크, HLS/DASH 파싱 | 선택 |

---

## 12. 결정 사항

### 확정 (2026-09-03)
| # | 안건 | 결정 |
|---|---|---|
| 1 | PO 토큰 | **외부 제공자 연동만** (자체 WebPO 발급 = 비목표) |
| 2 | JS solver | **clean-room 자체 작성** (yt-dlp 산출물 미사용) |
| 3 | 클라이언트 v1 | **visionos + web 둘 다** (무런타임 폴백 = visionos) |
| 4 | JS 런타임 의존 | **수용** — 우선순위: quickjs-ng CLI → node → deno. 인프로세스 임베드(pip quickjs)는 M0 스파이크 후 선택 채택 |

### 잔여 오픈
- HLS/DASH 매니페스트 포맷 v1 포함 여부 (권장: 제외, direct URL만)
- 병렬 Range 청크 v1.1 확정 여부
- PyPI 패키지명 `ydpy` 충돌 확인
- 쿠키/로그인(인증 클라이언트) v1.1+ 여부
- 외부 pot provider 기본값: bgutil 연동 예제를 저장소에 포함할지
