"""라인 사전 (line_fact v2) 테스트 — append-only + revoked + quarantine.

테스트 범위:
- learn: 정답 적립, observations 누적 (append-only), 충돌 시 기존 유지
- narrow_candidates: 향으로 좁히기, 없는 호 생성 불가
- revoke: 철회 (revoked=True, 삭제 아님, 데이터 보존)
- check_conflict: 같은 키 다른 향 감지
- quarantine: 충돌 시 confidence 낮춤
- 4중 가드: ledger 교집합 / 단일성 / 층 일관 / revoked
- 사전 단독 호 확정 불가 (narrow 만, 확정은 pipeline)
"""

from __future__ import annotations

from src.dictionary import LineFact, LineFactDictionary

# =========================================================================
# learn — 정답 적립 + append-only
# =========================================================================


class TestLearn:
    """learn: CLOSURE_LABEL 정답 적립 (append-only)."""

    def test_learn_creates_fact_observations_one(self) -> None:
        """Given: 빈 사전
        When: learn("A1", "101", "03", "S", "A", "auction")
        Then: LineFact 생성, observations=1"""
        dic = LineFactDictionary()
        fact = dic.learn("A1", "101", "03", "S", "A", "auction")
        assert isinstance(fact, LineFact)
        assert fact.complex_id == "A1"
        assert fact.dong == "101"
        assert fact.line == "03"
        assert fact.direction == "S"
        assert fact.area_type == "A"
        assert fact.observations == 1
        assert fact.revoked is False
        assert fact.confidence == 0.95

    def test_learn_same_key_increments_observations(self) -> None:
        """Given: learn("A1", "101", "03", "S", "A", "auction") 1회
        When: 같은 키로 learn 2회째
        Then: observations=2 (append-only, 덮어쓰기 아님)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        fact = dic.learn("A1", "101", "03", "S", "A", "rtms_registry_join")
        assert fact.observations == 2
        # direction/area_type 은 변경 없음 (append-only)
        assert fact.direction == "S"
        assert fact.area_type == "A"

    def test_learn_conflict_keeps_existing(self) -> None:
        """Given: learn("A1", "101", "03", "S", "A", "auction")
        When: 같은 키 다른 향("N") learn
        Then: 기존 유지 (observations=1, direction="S")"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        fact = dic.learn("A1", "101", "03", "N", "A", "auction")
        assert fact.direction == "S"
        assert fact.observations == 1


# =========================================================================
# narrow_candidates — 향으로 좁히기 + 없는 호 생성 불가
# =========================================================================


class TestNarrowCandidates:
    """narrow_candidates: 후보를 향으로 좁히기만 (없는 호 생성 불가)."""

    def test_narrow_by_direction(self) -> None:
        """Given: 사전에 ("A1","101","03")=S 학습됨
        When: narrow_candidates 에 S/N 두 후보
        Then: S 후보만 남음 (향으로 좁힘)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
            {"ho": "1503", "direction": "N", "floor": 15},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert len(result) == 1
        assert result[0]["direction"] == "S"
        assert result[0]["direction_match"] is True

    def test_narrow_cannot_create_ho(self) -> None:
        """Given: 빈 사전, 후보 2개
        When: narrow_candidates
        Then: 입력 후보 수 이하로만 반환 (새 호 생성 불가)"""
        dic = LineFactDictionary()
        candidates = [
            {"ho": "1503", "direction": "S"},
            {"ho": "1603", "direction": "N"},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert len(result) <= 2  # 좁히지 못해도 늘리지 않음
        # 결과에 입력에 없는 호가 없어야 함
        result_hos = {c["ho"] for c in result}
        assert result_hos.issubset({"1503", "1603"})

    def test_narrow_no_info_keeps_all(self) -> None:
        """Given: 빈 사전, 후보 2개
        When: narrow_candidates
        Then: 사전 정보 없어 좁히지 못함 — 둘 다 유지 (likely=False)"""
        dic = LineFactDictionary()
        candidates = [
            {"ho": "1503", "direction": "S"},
            {"ho": "1603", "direction": "N"},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert len(result) == 2
        assert all(c["likely"] is False for c in result)

    def test_narrow_single_candidate_likely(self) -> None:
        """Given: 사전에 ("A1","101","03")=S, 후보 중 S 하나만 남음
        When: narrow_candidates
        Then: 단일 후보 likely=True (확정 아님)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
            {"ho": "1503", "direction": "N", "floor": 15},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert len(result) == 1
        assert result[0]["likely"] is True


# =========================================================================
# revoke — 철회 (삭제 아님)
# =========================================================================


class TestRevoke:
    """revoke: 틀린 정답 철회 (revoked=True, 데이터 보존)."""

    def test_revoke_sets_revoked_get_returns_none(self) -> None:
        """Given: ("A1","101","03") 학습됨
        When: revoke("A1","101","03")
        Then: revoked=True, get → None"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        assert dic.revoke("A1", "101", "03") is True
        assert dic.get("A1", "101", "03") is None

    def test_revoke_preserves_data(self) -> None:
        """Given: ("A1","101","03") 학습 + revoke
        When: revoke 재호출
        Then: True 반환 (데이터 존재 — 삭제 아님)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.revoke("A1", "101", "03")
        # revoke 재호출 → True (fact 가 내부에 존재)
        assert dic.revoke("A1", "101", "03") is True
        # get_all 은 revoked 제외 → 빈 리스트
        assert dic.get_all("A1", "101") == []

    def test_revoke_nonexistent_returns_false(self) -> None:
        """Given: 빈 사전
        When: revoke("A1","101","03")
        Then: False (대상 없음)"""
        dic = LineFactDictionary()
        assert dic.revoke("A1", "101", "03") is False


# =========================================================================
# check_conflict / quarantine — 충돌 감지 및 보류
# =========================================================================


class TestConflictQuarantine:
    """check_conflict + quarantine: 충돌 감지 및 confidence 낮춤."""

    def test_check_conflict_different_direction(self) -> None:
        """Given: ("A1","101","03")=S 학습됨
        When: check_conflict("A1","101","03","N")
        Then: True (같은 키 다른 향)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        assert dic.check_conflict("A1", "101", "03", "N") is True

    def test_check_conflict_same_direction(self) -> None:
        """Given: ("A1","101","03")=S 학습됨
        When: check_conflict("A1","101","03","S")
        Then: False (향 일치)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        assert dic.check_conflict("A1", "101", "03", "S") is False

    def test_check_conflict_no_existing(self) -> None:
        """Given: 빈 사전
        When: check_conflict("A1","101","03","S")
        Then: False (기존 없음)"""
        dic = LineFactDictionary()
        assert dic.check_conflict("A1", "101", "03", "S") is False

    def test_quarantine_lowers_confidence(self) -> None:
        """Given: ("A1","101","03")=S (confidence=0.95) 학습됨
        When: quarantine("A1","101","03","N")
        Then: confidence=0.3 (낮춤), revoked=False (get 가능)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.quarantine("A1", "101", "03", "N")
        fact = dic.get("A1", "101", "03")
        assert fact is not None
        assert fact.confidence == 0.3
        assert fact.direction == "N"
        assert fact.revoked is False

    def test_quarantine_no_existing_creates_low_confidence(self) -> None:
        """Given: 빈 사전
        When: quarantine("A1","101","03","N")
        Then: confidence=0.3 fact 생성"""
        dic = LineFactDictionary()
        dic.quarantine("A1", "101", "03", "N")
        fact = dic.get("A1", "101", "03")
        assert fact is not None
        assert fact.confidence == 0.3
        assert fact.direction == "N"


# =========================================================================
# 4중 가드 — ledger 교집합 / 단일성 / 층 일관 / revoked
# =========================================================================


class TestFourGuards:
    """4중 가드: (1) ledger 교집합 (2) 단일성 (3) 층 일관 (4) revoked."""

    def test_guard1_ledger_intersection_filters_by_direction(self) -> None:
        """Guard 1 (ledger 교집합): 사전 정답과 향 불일치 후보 제외."""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.learn("A1", "101", "04", "N", "B", "auction")
        candidates = [
            {"ho": "1503", "direction": "N"},  # 03=S 인데 N → 제외
            {"ho": "1503", "direction": "S"},  # 03=S, S → 유지
            {"ho": "1504", "direction": "S"},  # 04=N 인데 S → 제외
            {"ho": "1504", "direction": "N"},  # 04=N, N → 유지
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        result_dirs = {(c["ho"], c["direction"]) for c in result}
        assert ("1503", "S") in result_dirs
        assert ("1504", "N") in result_dirs
        assert ("1503", "N") not in result_dirs
        assert ("1504", "S") not in result_dirs

    def test_guard2_singularity_likely_not_confirmed(self) -> None:
        """Guard 2 (단일성): 단일 후보 likely=True (confirmed 아님)."""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
            {"ho": "1503", "direction": "N", "floor": 15},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert len(result) == 1
        assert result[0]["likely"] is True
        # confirmed 필드는 없어야 함 (확정은 pipeline)
        assert "confirmed" not in result[0]

    def test_guard3_floor_consistency_flag(self) -> None:
        """Guard 3 (층 일관): 층 일치 시 floor_consistent=True."""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
            {"ho": "2503", "direction": "S", "floor": 25},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        # 사전에 line 03=S, 둘 다 S → 둘 다 유지, 층 2종 → inconsistent
        assert len(result) == 2
        assert all(c["floor_consistent"] is False for c in result)

    def test_guard3_floor_consistent_true(self) -> None:
        """Guard 3 (층 일관): 층 단일 시 floor_consistent=True."""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert result[0]["floor_consistent"] is True

    def test_guard4_revoked_excluded(self) -> None:
        """Guard 4 (revoked): revoked 라인 후보 제외."""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.revoke("A1", "101", "03")
        candidates = [
            {"ho": "1503", "direction": "S", "floor": 15},
            {"ho": "1503", "direction": "N", "floor": 15},
        ]
        result = dic.narrow_candidates("A1", "101", candidates)
        # 03 라인 revoked → 1503 후보 모두 제외
        assert len(result) == 0


# =========================================================================
# 사전 단독 호 확정 불가
# =========================================================================


class TestNoStandaloneConfirmation:
    """사전 단독으로 호 확정하지 않음 — narrow 만, 확정은 pipeline."""

    def test_narrow_returns_list_not_single_ho(self) -> None:
        """Given: 사전 학습 + 단일 후보
        When: narrow_candidates
        Then: 리스트 반환 (likely=True 가능, ho_final 없음)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        candidates = [{"ho": "1503", "direction": "S", "floor": 15}]
        result = dic.narrow_candidates("A1", "101", candidates)
        assert isinstance(result, list)
        assert "ho_final" not in result[0]
        assert "confirmed" not in result[0]

    def test_narrow_empty_candidates_returns_empty(self) -> None:
        """Given: 빈 후보 리스트
        When: narrow_candidates
        Then: 빈 리스트 (사전이 호를 만들지 않음)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        result = dic.narrow_candidates("A1", "101", [])
        assert result == []

    def test_narrow_never_invents_ho(self) -> None:
        """Given: 사전에 라인 03=S, 후보에 1503(S) 만 있음
        When: narrow_candidates
        Then: 결과 호는 입력에 있던 호만 (사전이 새 호 발명 안 함)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.learn("A1", "101", "04", "N", "B", "auction")
        candidates = [{"ho": "1503", "direction": "S"}]
        result = dic.narrow_candidates("A1", "101", candidates)
        result_hos = {c["ho"] for c in result}
        assert result_hos == {"1503"}  # 1504 발명 안 함


# =========================================================================
# get / get_all — 조회
# =========================================================================


class TestGetGetAll:
    """get / get_all 조회 동작."""

    def test_get_nonexistent_returns_none(self) -> None:
        """Given: 빈 사전
        When: get("A1","101","03")
        Then: None"""
        dic = LineFactDictionary()
        assert dic.get("A1", "101", "03") is None

    def test_get_all_returns_multiple_lines(self) -> None:
        """Given: 101동에 라인 03, 04 학습됨
        When: get_all("A1","101")
        Then: 2개 LineFact 반환"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.learn("A1", "101", "04", "N", "B", "auction")
        facts = dic.get_all("A1", "101")
        assert len(facts) == 2
        lines = {f.line for f in facts}
        assert lines == {"03", "04"}

    def test_get_all_excludes_revoked(self) -> None:
        """Given: 101동에 03, 04 학습, 03 revoke
        When: get_all("A1","101")
        Then: 04 만 반환 (revoked 제외)"""
        dic = LineFactDictionary()
        dic.learn("A1", "101", "03", "S", "A", "auction")
        dic.learn("A1", "101", "04", "N", "B", "auction")
        dic.revoke("A1", "101", "03")
        facts = dic.get_all("A1", "101")
        assert len(facts) == 1
        assert facts[0].line == "04"
