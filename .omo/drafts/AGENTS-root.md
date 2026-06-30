# AGENTS.md (루트 배포용 드래프트 — 첫 3줄 + `---` 제거 후 루트에 배포)

---

# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-29 (refreshed)
**VCS:** not a git repo (handoff package)
**Phase:** pre-implementation — plan complete, `src/` does not exist yet (Wave 1 creates it)

## OVERVIEW
아파트 호수(號數) 추론 엔진. 매물이 숨긴 정확한 동·호를 공공데이터 정답표(`unit_master`) + 다채널 증거 융합(Fellegi-Sunter)으로 추정. Stack: Python 3.12+ / pytest / dataclass / Supabase Pro. 141 레거시는 참고용; 본 플랜은 네이버 비의존·전국·재설계.

## STRUCTURE
```
부동산호수알아내기/
├── .omo/                    # 활성 플랜·드래프트·에비던스 (작업의 진실 소스)
│   ├── plans/apt-ho-resolver.md     # 33 todos + F1–F4, 6 waves, 37 commits
│   └── drafts/apt-ho-resolver.md    # 디폴트 A1–A90 + API키 인벤토리 (compaction-safe)
├── 건축HUB_대용량데이터/     # hub.go.kr 벌크 (Todo 6/8/9 메인 데이터 — 전유부·공동주택가격·주택인허가 호별개요)
├── 데이터_원본/              # 미확인 자료 4종 편입 (A87–A90, Todo 33)
│   ├── 법정동코드/           # 법정동코드 CSV 49,862행 (API보다 2배 풍부, 폐지동 포함)
│   ├── 건물DB_전체분/        # 17시도 build/jibun/road_code (V-World 건물DB, EUC-KR)
│   ├── 건축인허가_주택유형/  # mart_kcy_17.txt 263,778행 (오피스텔/도시형생활주택 식별)
│   ├── 단지_면적정보/        # xlsx 92,164행 (kaptCode 매핑 — V4/관리비 API 키)
│   └── 전유부_중복/          # 전유부 중복 다운로드 (참고용, 메인은 건축HUB_대용량데이터/)
├── 참고자료/
│   ├── 요약/                # 온보딩 요약 5종 (여기부터 읽기)
│   ├── 기획서_139/          # 1세대: 방법론·법적검토 + 141 헌장/PLAN/HANDOFF
│   ├── 분석문서_140/        # 2세대: 천장 17% 실측 (accuracy_diagnosis 최우선)
│   ├── 핵심코드_141최신/    # 3세대 레거시 코드 (참고만, 복사 금지)
│   └── 데이터샘플/          # 원베일리 골든셋 2,454건 + 실대장 + 분할다운로드(전유부 샘플 27개)
├── AGENTS.md                # 본 파일 (프로젝트 지식 베이스)
├── 부동산_공공API_정리.md    # API 13종 인벤토리 원본 (⚠️ 키 평문 — .gitignore 대상)
└── 새작업자에게_보내는메일.md # 141 시점 핸드오프 (서울경기 한정 — 현행 플랜은 전국)
```

## WHERE TO LOOK
| 할 일 | 위치 | 비고 |
|---|---|---|
| 플랜 실행 (`/start-work`) | `.omo/plans/apt-ho-resolver.md` | 33 todos, Wave 1→6 |
| 디폴트/결정 배경 | `.omo/drafts/apt-ho-resolver.md` | A1–A90, API키, 리서치 증거 |
| 온보딩 (141 철학) | `참고자료/요약/01_핵심요약_한장.md` + `새작업자에게_보내는메일.md` | |
| 141 레거시 참고 | `참고자료/핵심코드_141최신/` (closure/fusion/dictionary/legal_guard) | 복사 금지 |
| API 인벤토리 | `부동산_공공API_정리.md` (루트) + 드래프트 "API 키 인벤토리" 섹션 | 13종, 공통 인증키 |
| 골든셋 회귀 | `참고자료/데이터샘플/listings_원베일리_full.json`, `ledger_원베일리.json` | 2,454건, Wave 6 |
| 벌크 데이터 (메인) | `건축HUB_대용량데이터/` | 전유부 19,765,555행·공동주택가격·주택인허가 6,708,216행 |
| 참조 테이블 데이터 | `데이터_원본/` | 법정동코드·건물DB·kaptCode 매핑 (Todo 33) |

## CONVENTIONS (현행 플랜 결정사항)
- Python 3.12+ / pytest TDD / dataclass / 순수함수 우선. 141 코드 직접 복사 금지(참고만).
- Supabase Pro: 4개 스키마(core/api/ingest/private), 7개 테이블. RLS + `api` View(security_invoker)로 컬럼 보안.
- 대용량 적재 = `psql \COPY` 10만행 분할 + `ingest.progress` 재개 추적. Supabase client insert 금지(타임아웃).
- **전국 적재** (서울/경기 필터링 없음). 141 시점의 서울경기 한정은 레거시.
- 매칭 = **Fellegi-Sunter 단일 프레임워크**. m/u 확률은 라벨(Todo 18)에서 학습. 가중합 제거. DS는 충돌해결용만.
- 호 키 정합 = canonical `ho_id` 정규화 모듈(`src/ho_key.py`, Todo 31). 4개 소스 호 키 불일치 = 1번 엔지니어링 과제.
- 평형 → 정확 전용면적(cm²) + 타입(A/B/C). "평형" 매칭 금지(최고 판별자 버림).
- 전유부 역추론 배치도(Todo 32): 호 끝 2자리=라인, 라인별 면적 클러스터링 → 라인↔타입. **제일 큰 레버.**
- 2대 라벨원: 법원경매(full 동+호) + RTMS⋈집합건물등기 조인. RTMS 단독 라벨 불가.
- todo 포맷 = bare-number(1–33) + F1–F4. 에비던스 `.omo/evidence/task-N-apt-ho-resolver.<ext>`.
- **Hub API 호출 패턴 (VERIFIED)**: `requests.get(url, params={serviceKey:requests.utils.unquote(KEY),numOfRows:99999,sigunguCd,bjdongCd(소문자d,5자리),bun:zfill(4),ji:zfill(4)}, verify=False)`. urllib/https/대문자D/numOfRows=1 → 빈 응답.

## ANTI-PATTERNS (이 프로젝트에서 절대 금지)
- **네이버 비공식 API/크롤링** — 다윈중개 판례 배상. 플랜에서 완전 제거됨.
- **141 코드 복사** — 참고만. 특히 "naver" 하드코딩 5곳.
- **좌표(lat/lon) 영구 저장** — FORBIDDEN_FIELDS. V-World 지오코더 = 조회-사용-삭제 전용(A86).
- **가중합(0.30/0.30/0.25/0.15) / confidence 입력 / "평형" 매칭** — A84/A82로 제거.
- **"100% 확정" 과장** — 못 가르는 호는 `[{ho, probability}]` 리스트 출력(A81). P3 검증분만 "확정".
- **legal_guard 블랙리스트 방식** — 화이트리스트(STORABLE_FIELDS)만. 추정 표기 생략 금지.
- **소유자/연락처/가격/식별자 영구저장** — 개인정보보호법. 건물 구조까지만 영구.
- **서울 필터링 / Excel로 대용량 열기 / 한 번에 전체 COPY / urllib로 Hub 호출.**
- **백그라운드 에이전트·리뷰 무단 실행** — 비용 민감($20 이미 소진). 사용자 명시 승인 필요.

## UNIQUE STYLES
- 드래프트 A1–A90 = compaction-safe 디폴트 DB. 각 결정에 ID 부여 → 플랜·에비던스가 인용.
- 10가지 사고공식(GI/MDA/CC/PR/IS/IA/TE/CS/IL/IW) 적용해 통찰 도출(드래프트 섹션).
- 게이트: Metis gap analysis(bg_4b7c68ea) + dual-Momus 반영 완료 — 재실행 금지(비용).
- API 실증 프로브(2026-06-29): 10/13 API 스키마 확보, Hub 호출 패턴 확정 (드래프트 "VERIFIED API 스키마" 섹션).

## COMMANDS
```bash
# 아직 없음 — Wave 1 Todo 1이 환경 구성:
#   python -m venv .venv; pip install pytest httpx supabase python-dotenv PublicDataReader requests
#   python -m pytest tests/ -q
#   psql -h <DB_HOST> -c "\dt core.*"   # Supabase Pro
# .env (커밋 금지): SUPABASE_URL/ANON_KEY/SERVICE_KEY, PUBLIC_DATA_API_KEY, VWORLD_API_KEY, YOUTUBE_API_KEY, DEEPSEEK_API_KEY
```

## NOTES
- **kaptCode 매핑 해결 (A89)**: `데이터_원본/단지_면적정보/` xlsx 92,164행 = K-apt 단지면적. kaptCode(A10022877) + 주소 → V4·관리비 API 키 매핑 테이블 (Todo 33).
- **전유부 전용면적 주의 (Todo 9)**: 전유부(getBrExposInfo)에 area 없음 → 전유공용면적(getBrExposPubuseAreaInfo) 조인 필수 (mgmBldrgstPk 기준).
- VWORLD_API_KEY = `1F70B1E9-...` (만료 2026-12-29). `.env` 전용, 좌표 조회후파기(A86).
- PUBLIC_DATA_API_KEY = 공통 인증키 (13종 서비스, 무기한~2028-06-29). `부동산_공공API_정리.md`에 평문 — git 시 .gitignore 필수.
- 데이터 규모 ~5,179만행 ≈ 8GB (Supabase Pro 8GB 적합). `unit_master` 목표 3,291만행+.
- OpenCode 전용 (CLAUDE.md 비활성, `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1`). Windows PowerShell 환경.
- `.codegraph/` 존재하나 141 참고코드만 인덱스 — 프로젝트 코드(src/) 생기면 재인덱스 권장.
