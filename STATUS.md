# apt-ho-resolver — 작업 상태 (마지막: 2026-06-30)

## 📊 완료된 것
- ✅ 33/33 todos 완료 (코드 + 테스트)
- ✅ 629 tests passing, mypy 0 errors
- ✅ local.db 구축 (53M행, 10.5GB)
  - public_price 1,244만행 (동·호·면적·가격)
  - housing_permit 653만행 (pngtypGbNm·층)
  - building_registry 3,074만행 (동·호·층)
- ✅ 단지명 정규화 (3,237개 공백 충돌 해결)
- ✅ line_fact 892,850행 (66,960개 단지 라인→방향)
- ✅ 래미안원베일리 line_fact 교정 (10개 라인, confidence=1.0)
- ✅ view_ho.py / view_ho3d.py 시각화 도구 완성

## 🎯 정확도 현황
| 항목 | 정확도 | 근거 |
|------|--------|------|
| 면적+층 → 후보호 | 100% | 정부 원본 |
| area_type (pngtypGbNm) | 100% | 건축인허가 |
| direction | ~80% 추정 | 관례 기반 (실매물로 교정 가능) |

## ⏳ 대기 중
| 항목 | 상태 | 효과 |
|------|------|------|
| V-World 운영키 | 심사 중 | 건물 폴리곤 → direction 자동 검증 |
| **BLCM API 키** | **미신청** | 배치도+평면도 → direction 100% + 호 구분 |
| Supabase 프로젝트 | 미생성 | 실배포 |

## 🔑 현재 보유 키 (.env)
- PUBLIC_DATA_API_KEY=3d79e466...
- VWORLD_API_KEY=1F70B1E9...

## 🚀 재시작 명령어
```bash
# 프로젝트 루트
cd D:\부동산호수알아내기

# 가상환경 활성화
.\.venv\Scripts\activate

# DB 조회 (래미안원베일리 114동 25층 84L 남향)
python scripts/view_ho.py "래미안원베일리" 114 25 84L 남향
# → view_ho.html 생성 (지도 + 후보호)

# 3D 보기
python scripts/view_ho3d.py "래미안원베일리" 114 25 84L 남향

# 전체 테스트
python -m pytest tests/ -q
python -m mypy src/ --ignore-missing-imports

# line_fact 재구축 (새 데이터 적재 후)
python scripts/build_line_fact.py

# BLCM 키 발급받으러 가기
# https://blcm.go.kr → 회원가입 → API 신청 → DrawSearch.do
```

## 📝 할 일 (우선순위)
1. **BLCM API 키 발급** → blcm.go.kr 가서 신청
2. BLCM 키로 배치도+평면도 다운 → direction 100% + 호 구분
3. V-World 운영키 승인 대기
4. Supabase 프로젝트 생성 → DB 이관
