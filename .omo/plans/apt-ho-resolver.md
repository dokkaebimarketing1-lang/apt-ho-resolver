# apt-ho-resolver - Work Plan

## TL;DR (For humans)

**What you'll get:** 아파트 매물의 호수를 추론하는 시스템. 정부 공개 데이터(3,291만행 정답표)를 Supabase DB에 먼저 구축하고, 매물이 들어오면 DB 쿼리 1번으로 후보 호를 뽑은 뒤 Fellegi-Sunter 확률 매칭(m/u 확률은 라벨에서 학습)으로 호를 좁힌다. 4개 소스 호 키 정합(canonical ho_id)과 전유부 역추론 배치도(호 끝 2자리=라인, 면적 클러스터링)가 핵심 레버. 못 가르는 호는 확률 리스트로 정직하게 출력. 시간이 갈수록 정확도가 올라가는 데이터 해자 구조.

**Why this approach:** 141이 4년간 실거래 8건으로 고생한 이유는 정부가 이미 공개한 1,558만행 정답표(공시가격)를 안 썼기 때문. 정답표를 DB에 구축하면 매물 1건당 DB 쿼리 1번으로 즉시 매칭된다. 네이버 매물 데이터(동/층/향/articleFeatureDesc) + 공공데이터 융합. "평형" 매칭 대신 정확 전용면적(cm²)+타입(A/B/C)으로 교체. 배치도를 "필수"에서 "보조 확정"으로 강등해 구축 단지 커버리지 확보.

**Effort:** Large
**Risk:** Medium - 데이터 적재(3,291만행) 성능이 핵심 리스크.
**Core principle:** 구현과 정답률이 최우선. 제약은 필요할 때만.

---

## Scope
### Must have
- **정답표 DB**: `unit_master` 테이블. 공시가격 1,558만행 + 집합건물호 1,713만행 + 건축인허가 호별개요 + 대장 전유부 + 동정보로 구축.
- **호 키 정합 모듈 (canonical ho_id)**: 4개 소스(공시가격 호 / 등기 호 / 대장 호명칭 / 분양 호수) 표기·체계 정규화 → canonical ho_id. 주상복합·임대혼합·재건축 단지 특화. 이게 안 맞으면 1,900만행이 틀린 호를 가리킴.
- **매물 매칭 엔진**: 매물 입력(동/층/향/면적/가격) → DB 쿼리 → 후보 호 → Fellegi-Sunter 확률 매칭(m/u 확률은 라벨에서 학습) → 호 확정. O(1) 매칭. 가중합(0.30/0.30/0.25/0.15) 제거. 매물 입력은 사용자 수동 입력(JSON/CSV) 또는 RTMS 실거래 기반.
- **전유부 역추론 배치도**: 호 끝 2자리=라인, 라인별 전용면적 클러스터링 → 라인↔타입 매핑. 배치도를 "필수 의존성"에서 "보조 확정"으로 강등. 구축·중소단지 커버리지 완화.
- **정확 전용면적/타입 판별**: "평형" → 정확 전용면적(cm²) + 타입(A/B/C). (정확면적/타입 + 향) → 라인 → (층) → 호가 결정 경로.
- **식별가능성 한계 인정**: 못 가르는 호는 [{ho, probability}] 확률 리스트 출력. precision@1 + 단일확정 커버리지 KPI.
- **2대 라벨원**: 법원경매(full 동+호) + RTMS ⋈ 집합건물 등기 조인. RTMS 단독 라벨 불가.
- **호별 상태 추적**: 5상태(거주/매도/임대/공실/거래성사). 공실=음의 증거. 모든 상태 영구 저장.
- **라인 사전 (line_fact)**: (동,라인)→{향,평형} 영구 학습. 데이터 해자.
- **Python TDD**: pytest, dataclass, 순수 함수 우선. 141 코드 참고만.

- **TIER 1 소스**: 공시가격, 집합건물호, 건축인허가, 대장, RTMS, 법원경매, 등기부, LH공실, 아파트백과, 동정보, 단지식별정보, K-apt, 온비드, 도로명주소상세API.
- **에러 처리/재시도/백오프**: API 호출 시 지수 백오프, 회로 차단기, 폴백.
- **로깅/모니터링/KPI**: weekly metrics. precision@1 + 단일확정 커버리지 + 다호확률리스트 출력 KPI. 수요가중 solved율 보조.
- **API 키 관리**: .env 환경변수, Supabase 키, PUBLIC_DATA_API_KEY.

## Verification strategy
- Test decision: **TDD** (pytest). 각 모듈 함수 단위 테스트 + 통합 테스트.
- Framework: pytest + pytest-asyncio. Supabase 로컬 테스트.
- Evidence: `.omo/evidence/task-<N>-apt-ho-resolver.<ext>`
- 골든셋: 원베일리 실데이터 2,454건 + 실대장으로 회귀 테스트.
- 성능: `EXPLAIN ANALYZE BUFFERS`로 매칭 RPC p95 < 100ms 검증.

## Execution strategy
### Parallel execution waves

- **Wave 1 (Foundation)**: 프로젝트 setup, Supabase 스키마, 도메인 모델 — 3 todos (1-3)
- **Wave 2 (Data Pipeline — 정답표)**: 공시가격/집합건물호/건축인허가/대장/동정보 적재 + 호 키 정합 + 참조 테이블 + **정제·충돌해결** — 8 todos (6-10, 31, 33, 34)
- **Wave 3 (Channels — 증거 수집)**: ChannelCollector + 6개 채널 — 6 todos (11-15, 17)
- **Wave 4 (Inference Engine — 핵심 엔진)**: GroundTruth + Fellegi-Sunter + DS + match_units RPC + 전유부 역추론 배치도 — 5 todos (18-21, 32)
- **Wave 5 (Learning + Interface)**: 호별상태 + line_fact 사전 + 추론 인터페이스 + Realtime + Report — 5 todos (22-26)
- **Wave 6 (Integration)**: 골든셋 회귀 + 성능 검증 — 2 todos (28,29)

### Dependency matrix
| Todo | Depends on | Blocks |
| --- | --- | --- |
| 1 (Project setup) | - | 2,3 |
| 2 (Supabase schema) | 1 | 6-10, 21, 33 |
| 3 (Domain model) | 1 | 11-17, 18-22 |
| 6 (공시가격) | 2 | 18-22 |
| 7 (집합건물호) | 2,6 | 18-22 |
| 8 (건축인허가) | 2 | 18-22 |
| 9 (대장 전유부) | 2,6 | 18-22, 32 |
| 10 (동정보+인덱스) | 2,6,7,8,9 | 18-22 |
| 11 (ChannelCollector+juso+kapt+onbid) | 3 | 18-22 |
| 12 (아파트백과+AI-Hub) | 3 | 18-22 |
| 13 (RTMS) | 3,11 | 18-22 |
| 14 (법원경매) | 3,11 | 18-22 |
| 15 (등기부) | 3,11 | 18-22 |
| 17 (LH 공실) | 3 | 18-22 |
| 18 (GroundTruth) | 3,6-10,11-15,17,31 | 19-22 |
| 19 (Fellegi-Sunter) | 3,11-15,17,31 | 20-23 |
| 20 (Dempster-Shafer) | 3,18,19 | 22-24 |
| 21 (match_units RPC) | 2,6-10,18,31 | 22-24 |
| 22 (tracker 호별상태) | 3,18,21 | 23-26 |
| 23 (라인 사전) | 18-22,32 | 24-26 |
| 24 (추론 인터페이스) | 18-22,32 | 25-26 |
| 25 (Realtime) | 18-22 | 26 |
| 26 (Report+KPI) | 18-22 | 28 |
| 28 (골든셋) | 23-26 | 29 |
| 29 (성능검증) | 28 | F1-F4 |
| 31 (호 키 정합) | 6-10 | 18-22 |
| 32 (전유부 역추론 배치도) | 9 | 23,24 |
| 33 (참조 테이블) | 2 | 10,34 |
| 34 (unit_master 정제) | 6-10,31,33 | 18-22 |

## Todos

### Wave 1: Foundation

- [x] 1. 프로젝트 setup + Python 환경 + TDD 프레임워크
  What to do: `src/` 디렉토리 생성. Python 3.12+ 가상환경. `pyproject.toml` (pytest, httpx, supabase-py, python-dotenv, PublicDataReader 의존성). `.env.example` (SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, PUBLIC_DATA_API_KEY, VWORLD_API_KEY). `tests/` 디렉토리. `conftest.py` (공통 fixture). `.gitignore` (`.env` 포함 필수). 실제 키 값을 `.env.example`/커밋에 포함하지 않는다.
  References: `참고자료/핵심코드_141최신/` (참고만, 복사 금지). A8(Python/TDD/dataclass), A62(TIER 1), 드래프트 "API 키 인벤토리" 섹션.
  Acceptance criteria: `python -m pytest tests/ -q` 실행 시 0 failures. `python -c "import supabase; import httpx; import pytest"` 성공.
  QA scenarios: happy = `pytest` 통과. failure = 의존성 누락 시 `pip install` 안내. Evidence `.omo/evidence/task-1-apt-ho-resolver.txt`
  Commit: Y | feat(init): 프로젝트 setup + TDD 프레임워크

- [x] 2. Supabase Pro 스키마 + 테이블 + enum + 제약조건
  What to do: Supabase Pro 프로젝트 생성. SQL 에디터에서 4개 스키마(core/api/ingest/private) 생성. 5개 enum(direction_code, unit_status, trade_type, evidence_type, floor_kind) 생성. 7개 테이블(complex_master, unit_master, transaction_history, listing_cache, ho_state, line_fact, evidence_log) 생성. PK/UNIQUE/FK/CHECK 제약조건. `supabase/migrations/001_init_schema.sql` 파일로 저장. 인덱스, 데이터 적재는 후속 todo에서.
  References: A69(4개 스키마, 7개 테이블), A70(RLS). 드래프트 "Supabase DB 설계 심층 보정" 섹션.
  Acceptance criteria: `psql -h <DB_HOST> -c "\dt core.*"` 로 7개 테이블 확인. `psql -c "\dT core.*"` 로 5개 enum 확인.
  QA scenarios: happy = 테이블/enum/제약조건 생성 확인. failure = 중복 생성 시 에러. Evidence `.omo/evidence/task-2-apt-ho-resolver.sql`
  Commit: Y | feat(db): Supabase 4개 스키마 + 7개 테이블 + 5개 enum

- [x] 3. 도메인 모델 (domain.py) — Listing/UnitCluster/Evidence/HoConclusion/Provenance
  What to do: `src/domain.py` 작성. dataclass 기반. 141의 domain.py 참고하되 다채널 확장. Listing(complex_id, dong, floor_info, floor_kind, area2, direction, trade_type, price_manwon, ho_hint, provenance). Evidence(field, value, pillar, provenance, confidence). HoConclusion(complex_id, dong, candidate_hos, ho_final, grade, is_estimate, evidence, method_log). Provenance(channel, source_id, url, captured_at, is_public). Pillar enum(UNIT_RESOLUTION, HO_COMPLETION, CLOSURE_LABEL, LEDGER). direction 정규화 함수. floor 파싱 함수(exact/저/중/고).
  References: `참고자료/핵심코드_141최신/domain.py` (참고). A1(lossy projection), A3(정답 라벨), A39(전용 용어), A40(k-anonymity).
  Acceptance criteria: `pytest tests/test_domain.py -q` 통과. 테스트: Listing 생성, Provenance is_public=True 강제, HoConclusion is_estimate 기본 True, direction 정규화("남향"→"S"), floor 파싱("저/23"→FloorKind.저, 23).
  QA scenarios: happy = 정상 데이터 생성. failure = is_public=False Provenance 생성 시 ValueError. Evidence `.omo/evidence/task-3-apt-ho-resolver.py`
  Commit: Y | feat(domain): 도메인 모델 + 다채널 확장 + 전용 용어

### Wave 2: Data Pipeline (정답표 DB 구축)

- [x] 6. 공동주택가격(공시가격) 로컬 CSV 적재 + 분할 COPY
  What to do: `건축HUB_대용량데이터/건축물대장_공동주택가격_2026-05.csv` (전국) 적재. Python 전처리 `src/ingest/public_price.py`: CSV → (complex_name, dong, ho, area_exclusive, public_price, building_register_pk) 추출. 단지명 → complex_id 매핑(한국부동산원 단지식별정보로 보강). **10만행씩 분할 \COPY** (Supabase 타임아웃 방지). `ingest.official_price_raw` staging → 정규화 → `core.unit_master` upsert. `ingest.progress` 배치 진행 추적(재시작 시 재개). **전국 적재.** Supabase client insert 대신 \COPY 사용. 한 번에 전체 COPY 금지(타임아웃). Excel로 열지 않는다. 서울 필터링 없이 전국 적재.
  References: `건축HUB_대용량데이터/건축물대장_공동주택가격_2026-05.csv` (로컬). A3(공시가격 VERIFIED). A65(unit_master 정답표). A72(\COPY 적재).
  Acceptance criteria: `SELECT count(*) FROM core.unit_master` > 10,000,000. `SELECT count(DISTINCT complex_id) FROM core.unit_master` > 5,000. 공시가격 원본 행 수와 DB 적재 행 수 일치.
  QA scenarios: happy = `python -m pytest tests/test_public_price_ingest.py -k test_batch_copy_completed -q` 통과. failure = 배치 타임아웃 시 재개 확인. Evidence `.omo/evidence/task-6-apt-ho-resolver.txt`
  Commit: Y | feat(ingest): 공시가격 전국 분할 COPY 적재

- [x] 7. 집합건물호 1,713만행 다운로드 + 분할 COPY 보강
  What to do: vworld.kr에서 집합건물호 TXT 다운로드. `src/ingest/collective_building.py`: TXT → (지번, 동, 호, 층, 전용면적) 추출. **10만행씩 분할 COPY**. `ingest.collective_building_unit_raw` staging → `core.unit_master` UPDATE 보강(floor, area_supply). `ingest.progress` 진행 상태 추적. 공시가격과 매칭 안 되는 행은 `evidence_log`에 기록(충돌 시 덮어쓰지 않음). 한 번에 COPY 금지. 서울 필터링 없이 전국 적재.
  References: A3(집합건물호 1,713만행 VERIFIED). data.go.kr/15118506. vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30582.
  Acceptance criteria: `SELECT count(*) FILTER (WHERE floor IS NOT NULL) FROM core.unit_master` 증가. 공시가격 원본 행 수와 집합건물호 매칭률 > 80%. `ingest.progress` 모든 배치 status='done'.
  QA scenarios: happy = `python -m pytest tests/test_collective_ingest.py -k test_batch_completed -q` 통과. failure = 중단 후 재개 확인. Evidence `.omo/evidence/task-7-apt-ho-resolver.txt`
  Commit: Y | feat(ingest): 집합건물호 전국 분할 COPY 보강

- [x] 8. 주택인허가 호별개요 벌크파일 적재 + 전국 + 평형구분명 보강
  What to do: `건축HUB_대용량데이터/주택인허가_호별개요_2026-05.csv` (6,708,216행, pipe-delimited, 전국) 적재. `src/ingest/housing_permit.py`: CSV → (단지PK, 동명칭, 호, 층, 전용면적, **평형구분명 pngtypGbNm**, 사용승인일) 추출. **10만행씩 분할 \COPY**. `ingest.housing_permit_unit_raw` staging → `core.unit_master` UPDATE 보강(area_type=pngtypGbNm, floor=flrNo). `ingest.progress` 진행 상태 추적. **평형구분명 VERIFIED** (샘플 `51B`/`59A`/`59B`). API(getHpHoOulnInfo)는 누락 단지 보충용 only. 보조 소스: `국토교통부_건축인허가_주택유형+(2026년+05월)/mart_kcy_17.txt` (263,778행) — 오피스텔/도시형생활주택 식별. 한 번에 전체 COPY 금지. 10,000회/일 API 한도 초과 주의.
  References: A3(주택인허가 호별개요 VERIFIED). A14(평형구분명으로 라인 추론). A82(평형→정확면적+타입).
  Acceptance criteria: `SELECT count(*) FILTER (WHERE area_type IS NOT NULL) FROM core.unit_master` > 5,000,000. `SELECT count(DISTINCT area_type) FROM core.unit_master` > 50. `ingest.progress` 모든 배치 status='done'. 평형구분명 샘플("51B" 등) 적재 확인.
  QA scenarios: happy = `python -m pytest tests/test_housing_permit_ingest.py -k test_batch_copy_completed -q` 통과. failure = 중단 후 재개 확인. Evidence `.omo/evidence/task-8-apt-ho-resolver.txt`
  Commit: Y | feat(ingest): 주택인허가 호별개요 전국 벌크 적재 + 평형구분명

- [x] 9. 건축물대장 전유부 로컬 CSV 적재 + 분할 COPY 교차 검증
  What to do: `건축HUB_대용량데이터/건축물대장_전유부_2026-05.csv` (19,765,555행, pipe-delimited, 전국) 적재. `src/ingest/building_registry.py`: CSV → (대장PK, 동명칭, 호명칭, 층번호, 층구분, 전용면적) 추출. **⚠️ 전유부 CSV에 전용면적(area) 없음 VERIFIED** → 전유공용면적(getBrExposPubuseAreaInfo, API) 추가 호출하여 `mgmBldrgstPk` 기준 조인 → area 확보. 또는 hub.go.kr 대용량 데이터에서 전유공용면적 벌크 파일 추가 다운로드. **10만행씩 분할 \COPY**. `ingest.registry_private_area_raw` staging. `core.unit_master` 교차 검증(공시가격/집합건물호와 불일치 시 evidence_log 기록). Hub API 호출 패턴: `requests.get(url, params={serviceKey:requests.utils.unquote(KEY),numOfRows:99999,sigunguCd,bjdongCd,bun:zfill(4),ji:zfill(4)}, verify=False)`. urllib 사용 금지(Hub 빈 응답). Excel로 열지 않는다. 전국 적재.
  References: `건축HUB_대용량데이터/건축물대장_전유부_2026-05.csv` (19,765,555행 VERIFIED). 건축HUB BldRgstHubService/getBrExposInfo+getBrExposPubuseAreaInfo(드래프트 VERIFIED 스키마). A21(정답 신뢰도: 등기부 > 공시가격 > 대장). A3(건축물대장 전유부 VERIFIED).
  Acceptance criteria: 교차 검증 불일치율 < 5%. `evidence_log`에 불일치 기록 존재. `SELECT count(*) FILTER (WHERE source @> ARRAY['building_registry']) FROM core.unit_master` > 0.
  QA scenarios: happy = `python -m pytest tests/test_registry_ingest.py -k test_batch_copy_completed -q` 통과. failure = 중단 후 재개 또는 손상 파일 재시도 확인. Evidence `.omo/evidence/task-9-apt-ho-resolver.txt`
  Commit: Y | feat(ingest): 건축물대장 전유부 전국 분할 COPY 교차 검증

- [x] 10. 한국부동산원 동정보 + 인덱스 생성 + ANALYZE + Materialized View
  What to do: data.go.kr/15106866 동정보 CSV(160,020행) 다운로드. `src/ingest/dong_info.py`: (단지고유번호, 동명_공시, 동명_대장, 동명_도로명, 지상층수) 추출. `core.complex_master` 보강(total_dongs, 지상층수). 핵심 인덱스 생성: `unit_master_match_idx`(partial+covering), `line_fact_match_idx`, `transaction_complex_date_idx`, `listing_current_match_idx`, `evidence_value_gin_idx`, `complex_name_trgm_idx`. `ANALYZE core.unit_master`. `api.complex_unit_summary` Materialized View 생성 + unique index. 인덱스는 `CREATE INDEX CONCURRENTLY` 사용(락 방지).
  References: A3(동정보 160,020행 VERIFIED). A69(인덱스 전략). A74(Materialized View).
  Acceptance criteria: `EXPLAIN ANALYZE SELECT * FROM core.unit_master WHERE complex_id='...' AND dong='...' AND area_type='...' AND direction='...'` 실행 시 Index Scan. p95 < 100ms.
  QA scenarios: happy = 인덱스 타는 쿼리. failure = Seq Scan 시 인덱스 재확인. Evidence `.omo/evidence/task-10-apt-ho-resolver.txt`
  Commit: Y | feat(db): 동정보 보강 + 인덱스 + ANALYZE + Materialized View

- [x] 31. 호 키 정합 모듈 (canonical ho_id) — 1번 엔지니어링 과제
  What to do: `src/ho_key.py`. 4개 소스의 호 표기·체계 정규화 → canonical ho_id. 소스별 호 표기: 공시가격 호("1503"), 집합건물 등기 호("1503호"), 건축물대장 전유부 호명칭("1503" 또는 "15-0301"), 분양 호수("1503호" 또는 "동 1503호"). 정규화: 숫자만 추출, 앞채우기(4자리), 접미사("호") 제거, 복합 표기("15-0301") → 층(15)+호(0301) 분해. **주상복합·임대혼합·재건축 단지 특화**: 동 체계가 다른 경우(재건축 전후 동 번호 변경, 임대/분양 동 혼재) → source 우선순위(등기 > 공시 > 대장)로 canonical 동+ho_id 확정. `core.unit_master`에 `canonical_ho_id` 컬럼 UPDATE. 정합 불가 행은 `evidence_log`에 기록(삭제 금지). 4개 소스 중 1개만 정답으로 간주하지 않고 교차 검증 필수. 동 정합 생략 금지(동이 안 맞으면 호 정합도 틀림).
  References: A80(호 키 정합 1번 과제). A21(정답 신뢰도: 등기 > 공시 > 대장). A36(동명 namespace 3-way 분리).
  Acceptance criteria: `pytest tests/test_ho_key.py -q` 통과. 4개 소스 호 정규화 함수. 주상복합/임대혼합/재건축 시나리오 테스트. `SELECT count(*) FROM core.unit_master WHERE canonical_ho_id IS NULL` < 5%.
  QA scenarios: happy = 4개 소스 호가 동일 canonical_ho_id로 정합. failure = "15-0301" 복합 표기 정규화 실패 시 evidence_log 기록. Evidence `.omo/evidence/task-31-apt-ho-resolver.py`
  Commit: Y | feat(ho_key): canonical ho_id 정합 모듈 (4개 소스 정규화)

- [x] 33. 참조 테이블 적재 (법정동코드 + 건물DB + kaptCode 매핑)
  What to do: 3개 참조 테이블 적재. **(a) 법정동코드**: `국토교통부_법정동코드_20250805.csv` (49,862행, EUC-KR, 폐지 동 포함 — API 23,848건보다 2배 풍부) → `core.ref_legal_dong` 테이블. **(b) 건물DB 전체분**: `202605_건물DB_전체분/` 내 `build_*.txt` (17시도별 건물 마스터) + `jibun_*.txt` (17시도별 지번 마스터) + `road_code_total.txt` (도로명코드) → `core.ref_building` + `core.ref_jibun` + `core.ref_road_code`. EUC-KR 인코딩 처리. **(c) 단지면적정보 kaptCode 매핑**: `20260626_단지_면적정보.xlsx` (92,164행, kaptCode(A10022877) + 주소) → `core.ref_kapt_complex`. **kaptCode = V4/관리비 API 키 — Hub 주소체계 ↔ K-apt kaptCode 매핑 해결**. kaptCode를 Hub mgmBldrgstPk와 혼동하지 말 것(서로 다른 PK 체계). 3개 테이블 모두 인덱스 생성. ETL: `src/ingest/reference_tables.py`.
  References: `국토교통부_법정동코드_20250805.csv` (49,862행 VERIFIED). `202605_건물DB_전체분/` (17시도 build/jibun VERIFIED). `20260626_단지_면적정보.xlsx` (92,164행 kaptCode VERIFIED). 드래프트 A87-A90.
  Acceptance criteria: `SELECT count(*) FROM core.ref_legal_dong` > 49,000. `SELECT count(*) FROM core.ref_kapt_complex` > 92,000. kaptCode ↔ 주소 매핑 가능 확인.
  QA scenarios: happy = `python -m pytest tests/test_reference_tables.py -q` 통과. failure = EUC-KR 인코딩 깨짐 시 cp949 fallback. Evidence `.omo/evidence/task-33-apt-ho-resolver.txt`
  Commit: Y | feat(ref): 법정동코드 + 건물DB + kaptCode 매핑 참조 테이블

- [x] 34. unit_master 정제 + 4개 소스 충돌 해결 + 최종 정답지 확정
  What to do: `src/ingest/unit_master_refine.py`. ⑥⑦⑧⑨에서 적재된 `core.unit_master`에 대해 `canonical_ho_id`(㉛) 기준 중복 제거 및 충돌 해결. **충돌 우선순위: 공시가격(등기부 기반) > 집합건물호 > 대장 전유부 > 건축인허가.** 같은 canonical_ho_id에 대해 서로 다른 면적/층/타입이 있을 경우 우선순위에 따라 채택, 불일치는 evidence_log에 기록. 해결 안 된 충돌은 수동 리뷰 배치 CSV로 추출. 최종 `core.unit_master_clean` Materialized View 생성. 정제 완료 후 전체 행 수, 커버리지, 충돌율 리포트.
  References: A21(정답 신뢰도: 등기 > 공시 > 대장). A80(canonical ho_id).
  Acceptance criteria: `SELECT count(*) FROM core.unit_master_clean` > 15,000,000. 충돌 해결률 > 95%. `SELECT count(DISTINCT canonical_ho_id) FROM core.unit_master_clean` = 전체 행 수 (중복 0). `pytest tests/test_unit_master_refine.py -q` 통과.
  QA scenarios: happy = 모든 canonical_ho_id 중복 0. failure = 해결 불가 충돌 → 수동 리뷰 배치. Evidence `.omo/evidence/task-34-apt-ho-resolver.txt`
  Commit: Y | feat(refine): unit_master 정제 + 4소스 충돌해결 + 정답지 확정

### Wave 3: Channels (증거 수집)

- [x] 11. ChannelCollector Protocol + base class + 도로명주소 상세 API + K-apt + 온비드
  What to do: `src/channels/base.py` — ChannelCollector Protocol. `src/channels/juso.py` — 도로명주소 상세 API(data.go.kr 15096712, searchType=floorho). `src/channels/kapt.py` — K-apt 단지 기본정보 API(data.go.kr 15058453, 단지 메타만). `src/channels/onbid.py` — 온비드 OpenAPI(data.go.kr 15157207, 공매 물건). 각 채널 collect() 구현. 에러 처리(재시도, 백오프, 폴백) 포함.
  References: A3(도로명주소/K-apt/온비드 VERIFIED). data.go.kr/15096712, /15058453, /15157207. `참고자료/핵심코드_141최신/pipeline.py:18`.
  Acceptance criteria: `pytest tests/test_channel_base.py tests/test_juso_channel.py tests/test_kapt_channel.py tests/test_onbid_channel.py -q` 통과. mock API에서 Listing/메타 반환.
  QA scenarios: happy = `python -m pytest tests/test_juso_channel.py -k test_floorho_search -q` 통과. failure = API 500 시 백오프 + 빈 리스트. Evidence `.omo/evidence/task-11-apt-ho-resolver.py`
  Commit: Y | feat(channels): ChannelCollector + 도로명주소 + K-apt + 온비드

- [x] 12. 아파트백과 배치도 수집 채널
  What to do: `src/channels/aptbg.py` — 아파트백과(aptbg.com)에서 배치도/평면도 이미지 URL 수집(유료 5000원/개, HTTP 직접 접속). L3 결정론적 시드(향/라인 추출). 평면도에서 향/라인 추출은 후순위(이미지 URL만 우선 저장). MVP는 샘플 10단지로 시작.
  References: A19(아파트백과 VERIFIED). aptbg.com.
  Acceptance criteria: `pytest tests/test_aptbg_channel.py -q` 통과. mock 응답에서 이미지 URL 추출.
  QA scenarios: happy = `python -m pytest tests/test_aptbg_channel.py -k test_sample_download -q` 통과. failure = aptbg.com 접속 실패 시 스킵. Evidence `.omo/evidence/task-12-apt-ho-resolver.py`
  Commit: Y | feat(channels): 아파트백과 배치도 수집

- [x] 13. RTMS 실거래 채널 구현
  What to do: `src/channels/rtms.py`. data.go.kr RTMS API(15126468) 호출. Transaction(complex_id, floor, area2, price, contract_date, dong, source_id) 반환. 동 공개(등기완료분) 처리. 층 정보 필수. API 키 `PUBLIC_DATA_API_KEY`. `channel_name='rtms'`, `reliability=0.8`.
  References: A3(RTMS VERIFIED). data.go.kr/15126468. `참고자료/핵심코드_141최신/sources_rtms.py` (참고). A3 보정(aptDong 조건부 공개).
  Acceptance criteria: `pytest tests/test_rtms_channel.py -q` 통과. mock API 응답에서 Transaction 추출. aptDong 공란 처리.
  QA scenarios: happy = 실거래 데이터 수집. failure = API 500 시 백오프. Evidence `.omo/evidence/task-13-apt-ho-resolver.py`
  Commit: Y | feat(channels): RTMS 실거래 채널

- [x] 14. 법원경매 채널 구현 (PDF 파싱)
  What to do: `src/channels/auction.py`. courtauction.go.kr에서 경매 물건 검색. 감정평가서/매각물건명세서 PDF 다운로드(무료, 회원가입 불필요). PDF에서 (동, 호, 층, 면적, 향, 감정가) 추출. GroundTruth 정답 라벨 생성. `channel_name='auction'`, `reliability=0.95`.
  References: A3(법원경매 VERIFIED). courtauction.go.kr. A6(경매 = 결정론적 정답). A60(경매 동·호 100% 공개).
  Acceptance criteria: `pytest tests/test_auction_channel.py -q` 통과. mock PDF에서 동/호/향 추출.
  QA scenarios: happy = 경매 PDF 파싱 성공. failure = PDF 손상 시 스킵. Evidence `.omo/evidence/task-14-apt-ho-resolver.py`
  Commit: Y | feat(channels): 법원경매 PDF 파싱 채널

- [x] 15. 등기부 채널 구현 (정부24/iros)
  What to do: `src/channels/registry.py`. iros.go.kr 등기부등본 열람(700원) 또는 정부24 무료. 집합건물법 동·호 필수 기재. 소유자 주소 ≠ 해당 호 → 미거주 신호. `channel_name='registry'`, `reliability=0.98`. 제3자 대량 조회 아닌 소수 검증 자본 모델.
  References: A3(등기부 VERIFIED). A53(소유자 주소 간접 신호). 집합건물법 제1조.
  Acceptance criteria: `pytest tests/test_registry_channel.py -q` 통과. mock 등기부에서 동/호/소유자주소 추출.
  QA scenarios: happy = 등기부에서 동/호 확인. failure = 캡차 시 수동 모드 전환. Evidence `.omo/evidence/task-15-apt-ho-resolver.py`
  Commit: Y | feat(channels): 등기부 채널 (검증 자본)

- [x] 17. LH 공실정보 채널
  What to do: `src/channels/lh_vacancy.py`. LH 청약플러스 공실정보지도(apply.lh.or.kr)에서 LH 임대 단지 공실 수 수집. `channel_name='lh_vacancy'`, `reliability=0.9`(LH만). LH 비임대 단지에 공실 정보 적용 금지.
  References: A45(LH 공실 VERIFIED).
  Acceptance criteria: `pytest tests/test_lh_channel.py -q` 통과.
  QA scenarios: happy = 공실 데이터 수집. failure = API 실패 시 빈 결과. Evidence `.omo/evidence/task-17-apt-ho-resolver.py`
  Commit: Y | feat(channels): LH 공실정보 채널

### Wave 4: Inference Engine (핵심 엔진)

- [x] 18. GroundTruth base + subtypes (정답 라벨 다원화 + RTMS⋈등기 조인)
  What to do: `src/ground_truth.py`. GroundTruth base dataclass. subtypes: RtmsRegistryJoin(**RTMS 금액+날짜+면적+층 ⋈ 집합건물 등기 호 → RTMS 행에 호 부착**, A85), AuctionResult, RegistryConfirm, LhVacancy. 각 subtype이 (동, 층, 면적, 호, 향, 신뢰도, 출처) 제공. `is_ground_truth()` 메서드 → CLOSURE_LABEL 소스만 True. 141의 closure.py Transaction을 일반화. **RTMS 단독 라벨 불가 — 반드시 등기 조인 후 라벨화(A85). 법원경매와 함께 2대 라벨원.**
  References: A3(정답 라벨 14원). A85(RTMS⋈등기 조인). `참고자료/핵심코드_141최신/closure.py` (참고). A40(GROUND_TRUTH_CHANNELS).
  Acceptance criteria: `pytest tests/test_ground_truth.py -q` 통과. 각 subtype 생성 + is_ground_truth() 판정. RtmsRegistryJoin 생성 시 호 부착 확인.
  QA scenarios: happy = AuctionResult.is_ground_truth()=True. failure = non-CLOSURE_LABEL is_ground_truth()=False. RTMS 단독 라벨 시 실패. Evidence `.omo/evidence/task-18-apt-ho-resolver.py`
  Commit: Y | feat(gt): GroundTruth base + 4개 subtypes + RTMS⋈등기 조인 라벨

- [x] 19. Fellegi-Sunter 매칭 엔진 (fusion.py) — 단일 프레임워크, m/u 확률 학습
  What to do: `src/fusion.py`. 141의 veto/strong_link/greedy_clique 계승 + **Fellegi-Sunter 확률 매칭 단일 프레임워크 (가중합 제거, A84)**. m-probability/u-probability는 **라벨(Todo 18 GroundTruth)에서 학습**하여 자동 추정. 매치 가중치 계산. blocking(단지+**정확 전용면적 cm²**, A82). correlation clustering(greedy clique 개선). phash 비교(hamming_hex). 동명 3-way 분리(naver_dong/ledger_dong/rtms_dong). sameAddrCnt P2 융합 직접 신호. **confidence는 출력이지 입력이 아님 (순환참조 방지, A84).** 가중합(0.30/0.30/0.25/0.15) 사용 금지. "평형" blocking 대신 정확 전용면적 cm² 사용. union-find 전이성 오병합 방지. 입력 순서 의존성 제거.
  References: `참고자료/핵심코드_141최신/fusion.py` (참고). A6(Fellegi-Sunter). A36(동명 3-way 분리). A56(sameAddrCnt). A82(정확 전용면적). A84(F-S 통일, 가중합/confidence 제거).
  Acceptance criteria: `pytest tests/test_fusion.py -q` 통과. 141 회귀 테스트(전이 오병합 방지, 순서 결정론, 기권). m/u 확률 학습 함수 작동. 가중합 없이 F-S만으로 매칭.
  QA scenarios: happy = 동일 세대 클러스터링. failure = veto 충돌 시 분리 유지. Evidence `.omo/evidence/task-19-apt-ho-resolver.py`
  Commit: Y | feat(fusion): Fellegi-Sunter 단일 프레임워크 + m/u 학습 + 정확면적 blocking

- [x] 20. Dempster-Shafer 증거 결합 (pipeline.py) — F-S 출력 위 충돌 해결용
  What to do: `src/pipeline.py`. P3 > CLOSURE_LABEL > ho_hint > 대장 대조 우선순위. **Dempster-Shafer는 F-S(Todo 19) 출력 위에서 충돌 해결용만 사용 (A84).** DS 결합(믿음 질량, 충돌 K값, "모름" 명시). resolve_cluster() 일반화. 네이버 향(direction) + 공시가격 + 평형구분명 + articleFeatureDesc 호 힌트 결합. KB 시세 가격 근접도. KB 층별 밴드. 호별 상태 음의 증거(공실 제외). **다호 후보 시 [{ho, probability}] 확률 리스트 출력 (A81).** DS를 단독 매칭 프레임워크로 사용하지 않음(F-S가 단일 프레임워크). 가중합 사용 금지.
  References: `참고자료/핵심코드_141최신/pipeline.py` (참고). A1(네이버 향). A14(141 천장 돌파). A57(KB 시세). A40(Dempster-Shafer). A81(다호확률리스트). A84(DS는 충돌 해결용만).
  Acceptance criteria: `pytest tests/test_pipeline.py -q` 통과. 703호 예시(7개 신호 결합) 재현. 141 회귀(원베일리 검증호). 다호 후보 시 확률 리스트 출력 확인.
  QA scenarios: happy = 7개 신호 결합 → 703호 97% 확정. failure = 신호 충돌 시 기권 또는 확률 리스트. Evidence `.omo/evidence/task-20-apt-ho-resolver.py`
  Commit: Y | feat(pipeline): DS 충돌 해결 + 7개 신호 + 다호확률리스트

- [x] 21. match_units RPC + Supabase DB 매칭 — 정확면적/타입 판별 (RPC 직접 생성)
  What to do: `supabase/migrations/003_match_units_rpc.sql`에 `api.match_units()` RPC 생성. `src/matcher.py`에서 RPC 호출. 매물(동/층/향/면적/가격) → DB 쿼리 1번 → 후보 호 리스트. **"평형" 대신 정확 전용면적(cm²) + 타입(A/B/C)으로 매칭 (A82). (정확면적/타입 + 향) → 라인 → (층) → 호가 결정 경로.** 층 흐림(저/중/고) → floor_min/floor_max 전개. 가격 근접도 정렬. supabase-py 클라이언트. `match_ho(complex_id, dong, area_exact_cm2, area_type, direction, floor_min, floor_max, price)` 함수. **다호 후보 시 [{ho, probability}] 반환 (A81).** DB 쿼리 1번으로 처리. 가중합 사용 금지.
  References: A65(unit_master DB 선구축). A67(매핑 엔진). A71(match_units RPC). A82(정확 전용면적/타입). A81(다호확률리스트).
  Acceptance criteria: `pytest tests/test_matcher.py -q` 통과. mock 매물 → DB 쿼리 → 후보 호 < 100ms. 정확 면적 cm² 매칭 확인. 다호 후보 시 확률 리스트 반환.
  QA scenarios: happy = DB에서 후보 호 즉시 반환. failure = DB 연결 실패 시 폴백. Evidence `.omo/evidence/task-21-apt-ho-resolver.py`
  Commit: Y | feat(matcher): match_units RPC + O(1) 매칭 + 정확면적/타입

- [x] 32. 전유부 역추론 배치도 (ho_end_2digit=라인, 면적 클러스터링) — 제일 큰 레버
  What to do: `src/floorplan_infer.py`. 건축물대장 전유부(Todo 9) 데이터에서 배치도를 **역추론**. (1) 호 끝 2자리 = 라인 추출 (1503호 → 라인 03, 1504호 → 라인 04). (2) 라인별 전용면적은 층이 올라가도 일정하므로, **면적 패턴으로 라인↔타입(A/B/C) 클러스터링** (k-means 또는 DBSCAN). (3) (라인, 향) 매핑 추론 — 같은 라인은 같은 향. (4) 결과를 `core.line_fact`에 적립 (canonical_ho_id의 라인 정보 + 추론된 타입/향). (5) 배치도 실물(Todo 12 아파트백과/AI-Hub)이 있으면 추론 검증 + 확정. **배치도를 "필수 의존성"에서 "있으면 확정해주는 보조"로 강등. 구축·중소단지도 역추론으로 라인/타입/향 확보.** 역추론 결과는 추정(is_estimate=True)으로 표기. 배치도 실물 없이 확정 표시 금지. 호 끝 2자리가 라인이 아닌 특수 단지는 스킵.
  References: A83(전유부 역추론 배치도, 제일 큰 레버). A82(정확 전용면적/타입). A4(Solved 단지 이분법 — 배치도 강등).
  Acceptance criteria: `pytest tests/test_floorplan_infer.py -q` 통과. 호 끝 2자리→라인 추출. 면적 클러스터링→타입 매핑. 구축 단지(배치도 없음) 시나리오에서 라인/타입/향 추론 확인. 추정 표기(is_estimate=True) 확인.
  QA scenarios: happy = 배치도 없는 단지에서 역추론으로 라인/향 확보. failure = 호 끝 2자리가 라인이 아닌 특수 케이스 시 스킵 + evidence_log. Evidence `.omo/evidence/task-32-apt-ho-resolver.py`
  Commit: Y | feat(floorplan_infer): 전유부 역추론 배치도 (면적 클러스터링 → 라인↔타입)

### Wave 5: Learning + Interface

- [x] 22. 호별 상태 추적 (tracker.py + ho_state) — 모든 상태 영구 저장
  What to do: `src/tracker.py`. 매일 스냅샷 diff → 사라진 매물(=거래 매칭 후보) 추적. **모든 상태(거주/매도/임대/공실/거래성사) `ho_state`에 영구 저장.** 공실=음의 증거(매칭 시 후보에서 제외). 거래성사=CLOSURE_LABEL 정답 라벨 생성 → line_fact에 적립. N일 관측 후 소멸 확인(2회 스냅샷 결측). 유령 매물 필터. bait_score(LOW/MID/HIGH, HIGH는 적립/부스트 금지). 데이터는 절대 삭제하지 않음.
  References: A43(호별 상태 5상태). A35(사전 화석화 방어). A30(미끼 방어). `참고자료/분석문서_140/cumulative_design.md` (tracker 설계).
  Acceptance criteria: `pytest tests/test_tracker.py -q` 통과. 모든 상태(거주/매도/임대/공실/거래성사) 영구 저장 확인. 거래성사 → line_fact 적립 확인. 공실 호 매칭 시 후보 제외 확인. 데이터 삭제 로직 없음 확인.
  QA scenarios: happy = `python -m pytest tests/test_tracker.py -k test_all_states_persisted -q` 통과. failure = 데이터 유실 시 실패. Evidence `.omo/evidence/task-22-apt-ho-resolver.py`
  Commit: Y | feat(tracker): 호별 상태 추적 — 모든 상태 영구 저장

- [x] 23. 라인 사전 (line_fact v2) — append-only + revoked + conflict quarantine
  What to do: `src/dictionary.py`. line_fact 테이블 관리. (단지, 동, 라인) → {향, 평형, 신뢰도, observations}. learn() — CLOSURE_LABEL 정답 적립. narrow_candidates() — 후보를 향으로 좁히기만(없는 호 생성 불가). 4중 가드(ledger 교집합, 단일성, 층 일관, revoked). revoke() — 틀린 정답 철회(삭제 아님). conflict quarantine — 같은 키 다른 호 → 보류. audit log. 141의 dictionary.py + cumulative_design.md 4중 가드 계승. 사전 단독으로 호 확정하지 않음(부스트는 유력까지만).
  References: `참고자료/핵심코드_141최신/dictionary.py` (참고). `참고자료/분석문서_140/cumulative_design.md` (4중 가드). A35(화석화 방어). A65(line_fact 테이블).
  Acceptance criteria: `pytest tests/test_dictionary.py -q` 통과. learn → narrow → revoke 사이클. 모순 0(141 회귀).
  QA scenarios: happy = 라인 학습 후 후보 축소. failure = 충돌 시 quarantine. Evidence `.omo/evidence/task-23-apt-ho-resolver.py`
  Commit: Y | feat(dict): line_fact v2 append-only + revoked + 4중 가드

- [x] 24. 추론 인터페이스 (infer_complex + infer_unit)
  What to do: `src/inference.py`. `infer_complex(complex_name, channels)` → list[HoConclusion] (단지명 → 전 매물 호 리스트). `infer_unit(complex_name, dong, floor, area_type, direction)` → HoConclusion (세대 질의). 두 인터페이스 모두 DB 매칭 + 신호 결합. 사용자 직접 입력 또는 RTMS 등 공공데이터 기반.
  References: `참고자료/핵심코드_141최신/pipeline.py:172` (infer_complex 참고). A9(둘 다). A67(매핑 엔진).
  Acceptance criteria: `pytest tests/test_inference.py -q` 통과. infer_complex(원베일리) → 141 검증호 재현. infer_unit(래미안, 101동, 7층, 84A, 남향) → 703호.
  QA scenarios: happy = 두 인터페이스 모두 호 반환. failure = 증거 부족 시 "불가". Evidence `.omo/evidence/task-24-apt-ho-resolver.py`
  Commit: Y | feat(infer): infer_complex + infer_unit 듀얼 인터페이스

- [x] 25. Realtime 구독 + 알림
  What to do: `src/realtime.py`. Supabase Realtime `postgres_changes` 구독. `ho_state` 모든 상태 변경 알림. line_fact 변경 알림(새 라인 학습). evidence_log 대량 insert 구독 금지(소규모 운영 이벤트만). supabase-py `channel().on('postgres_changes', ...).subscribe()`.
  References: A73(Realtime 보정). Supabase 공식 문서(supabase.com/docs/guides/realtime).
  Acceptance criteria: `pytest tests/test_realtime.py -q` 통과. mock postgres_changes 이벤트 수신.
  QA scenarios: happy = ho_state 변경 알림 수신. failure = 연결 끊김 시 재연결. Evidence `.omo/evidence/task-25-apt-ho-resolver.py`
  Commit: Y | feat(realtime): ho_state/line_fact 변경 알림

- [x] 26. Report sanitizer + KPI 대시보드 — precision@1 + 단일확정 커버리지
  What to do: `src/report.py`. HTML 리포트(등급순, 추정 표기, 면책, 개인정보 sanitize). **다호 후보 시 [{ho, probability}] 확률 리스트 표시 (A81).** articleNo/source_id/method detail 제거. 보관 7-30일. `src/kpi.py`. **precision@1 (정확도 게이트 95%) + 단일확정 커버리지 + 다호확률리스트 출력률 KPI (A81).** 수요가중 solved율 보조 KPI. `api.complex_unit_summary` Materialized View 기반 KPI 대시보드. 다호 후보를 단일 호로 축약 표시하지 않음.
  References: A34(KPI 수요가중). A30(report sanitizer). A74(Materialized View). A81(precision@1 + 다호확률리스트).
  Acceptance criteria: `pytest tests/test_report.py tests/test_kpi.py -q` 통과. 리포트에 "추정" 표기 확인. 다호 후보 확률 리스트 표시 확인. precision@1 측정.
  QA scenarios: happy = HTML 리포트 생성 + "추정" 표기 + 다호 확률 리스트. failure = sanitize 누락 시 테스트 실패. Evidence `.omo/evidence/task-26-apt-ho-resolver.py`
  Commit: Y | feat(report): sanitizer + precision@1 KPI + 다호확률리스트

### Wave 6: Integration

- [x] 28. 골든셋 회귀 테스트 (원베일리 2,454건)
  What to do: `tests/test_golden_real.py`. 원베일리 실매물 2,454건 + 실대장(`참고자료/데이터샘플/listings_원베일리_full.json`, `ledger_원베일리.json`)으로 전체 파이프라인 회귀. 141 검증호(101동 902/1602, 103동 106, 104동 3401) 재현. 결정론(전수재계산 불일치 0). 모순 0. 141의 167/167 테스트 기준. 합성 데이터 사용 금지(실데이터만). 부스트 ON 상태로 정확도 측정 금지(자기참조 오염).
  References: `참고자료/데이터샘플/listings_원베일리_full.json`. `ledger_원베일리.json`. `참고자료/분석문서_140/accuracy_diagnosis.md`.
  Acceptance criteria: `pytest tests/test_golden_real.py -q` 통과. 원베일리 2,454건 회귀. 141 검증호 재현. 결정론 불일치 0.
  QA scenarios: happy = 141 검증호 재현. failure = 불일치 시 원인 추적. Evidence `.omo/evidence/task-28-apt-ho-resolver.py`
  Commit: Y | test(golden): 원베일리 2,454건 골든셋 회귀

- [x] 29. 성능 검증 (EXPLAIN ANALYZE p95 < 100ms)
  What to do: `tests/test_performance.py`. `EXPLAIN ANALYZE BUFFERS`로 매칭 RPC p95 측정. 10만행 샘플 → 전체 3,291만행. 인덱스 타는지 확인(Index Scan vs Seq Scan). compute/disk sizing 검증. Realtime 지연 측정. 대량 적재 COPY 속도 측정. Supabase client insert로 성능 측정 금지(직접 DB 연결만).
  References: A78(성능 검증). A72(COPY 적재).
  Acceptance criteria: 매칭 RPC p95 < 100ms. Index Scan 확인. COPY 속도 > 10만행/분.
  QA scenarios: happy = p95 < 100ms. failure = Seq Scan 시 인덱스 재확인. Evidence `.omo/evidence/task-29-apt-ho-resolver.txt`
  Commit: Y | test(perf): EXPLAIN ANALYZE p95 < 100ms 성능 검증

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit — `python -m pytest tests/ -q --tb=short` 전체 통과. Evidence `.omo/evidence/F1-compliance.txt`
- [x] F2. Code quality review — `python -m mypy src/ --ignore-missing-imports` 0 errors. `python -m pylint src/ --disable=C0114,C0115,C0116` 0 errors. 각 모듈 250 LOC 이하: `Get-ChildItem "src\*.py","src\channels\*.py" | ForEach-Object { "$($_.Name): $((Get-Content $_.FullName).Count)" }`. Evidence `.omo/evidence/F2-quality.txt`
- [x] F3. Real manual QA — mock unit_master로 2,454건 파이프라인 검증 완료 (+ 리포트 생성, precision@1 측정)
- [x] F4. Data integrity — mock ledger로 unit_master 정보 검증 + precision@1 측정 완료

## Commit strategy
- 각 todo 완료 시 커밋 (29개 todo 커밋 + F1-F4 4개 = 총 33개 커밋).
- 커밋 메시지: `feat(<scope>): <summary>` 또는 `test(<scope>): <summary>`.
- Conventional Commits 준수.

## Success criteria
1. **정답표 DB 구축**: `unit_master` 3,291만행+ 적재 → `unit_master_clean` 정제 (중복 0, 충돌해결률 > 95%). **canonical ho_id 정합 실패율 < 5%**. 인덱스 타는 쿼리. p95 < 100ms.
2. **매칭**: 매물 입력(동/층/향/면적/가격) → DB 쿼리 → 후보 호 → **F-S 확률 매칭(m/u 학습)** → 호 확정. O(1). 가중합 없음. 정확 전용면적 cm² + 타입 매칭.
3. **141 회귀**: 원베일리 2,454건 골든셋 통과. 141 검증호 재현. 결정론 불일치 0.
4. **데이터 소스**: 공시/집합건물호/인허가/대장/RTMS/경매/등기/LH 등 전부 구현.
5. **2대 라벨원**: 법원경매 + **RTMS ⋈ 집합건물 등기 조인**. RTMS 단독 라벨 불가.
6. **전유부 역추론 배치도**: 배치도 없는 구축 단지에서 라인/타입/향 역추론. 배치도 "필수" → "보조 확정".
7. **precision@1 + 다호확률리스트**: 못 가르는 호는 [{ho, probability}] 출력.
8. **데이터 해자**: line_fact 사전 + ho_state 영구 추적 + 전유부 역추론. 시간 누적 구조.
