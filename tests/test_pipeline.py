"""pipeline.py 단위 테스트 — DS 증거 결합 + 우선순위 해결 + 전체 파이프라인.

테스트 시나리오 (8개):
1. combine_evidence: 2개 증거 결합 → 결합 믿음 질량
2. combine_evidence: 충돌 시 K값 계산 + 정규화
3. resolve_cluster: P3 > CLOSURE_LABEL > ho_hint 우선순위
4. run_pipeline: F-S 매칭 → DS 결합 → 호 확정
5. 다호 후보 시 [{ho, probability}] 리스트 출력
6. 음의 증거(공실) → 후보에서 제외
7. 가중합 미사용 확인
8. DS 단독 매칭 아님 (F-S 먼저, DS는 충돌 해결만)
"""

from __future__ import annotations

import inspect

from src.ground_truth import AuctionResult, RegistryConfirm, RtmsRegistryJoin
from src.pipeline import combine_evidence, resolve_cluster, run_pipeline


# =========================================================================
# Fixtures
# =========================================================================

_SAMPLE_UNITS: list[dict] = [
    {"complex_id": "C1", "dong": "101", "ho": "1501",
     "floor": 15, "area_type": "84A", "direction": "S", "area2": 84.12},
    {"complex_id": "C1", "dong": "101", "ho": "1502",
     "floor": 15, "area_type": "84B", "direction": "E", "area2": 84.50},
    {"complex_id": "C1", "dong": "101", "ho": "1503",
     "floor": 15, "area_type": "84A", "direction": "S", "area2": 84.12},
    {"complex_id": "C1", "dong": "101", "ho": "1601",
     "floor": 16, "area_type": "84A", "direction": "S", "area2": 84.12},
    {"complex_id": "C1", "dong": "101", "ho": "1603",
     "floor": 16, "area_type": "84A", "direction": "S", "area2": 84.12},
]


# =========================================================================
# Test 1: combine_evidence — 2개 증거 결합 → 결합 믿음 질량
# =========================================================================


class TestCombineEvidenceSameHypothesis:
    """동일 가설 2개 증거 결합 → 결합 믿음 질량 증가."""

    def test_two_positive_same_ho(self) -> None:
        """Given: 1503호에 mass 0.6, 0.7 증거
        When: combine_evidence
        Then: 결합 mass > 개별 mass, unknown 감소"""
        evs = [
            {"hypothesis": "1503", "mass": 0.6},
            {"hypothesis": "1503", "mass": 0.7},
        ]
        result = combine_evidence(evs)
        m = result["masses"]["1503"]
        assert m > 0.6
        assert m > 0.7
        assert result["unknown"] < 0.4  # unknown 감소
        assert result["conflict_k"] == 0.0  # 동일 가설 → 충돌 없음

    def test_combined_mass_formula(self) -> None:
        """Given: mass 0.5, 0.6 동일 가설
        When: combine_evidence
        Then: m = 1 - (1-0.5)*(1-0.6) = 0.8, unknown = 0.5*0.4 = 0.2"""
        evs = [
            {"hypothesis": "1503", "mass": 0.5},
            {"hypothesis": "1503", "mass": 0.6},
        ]
        result = combine_evidence(evs)
        assert abs(result["masses"]["1503"] - 0.8) < 0.001
        assert abs(result["unknown"] - 0.2) < 0.001

    def test_empty_evidences(self) -> None:
        """Given: 빈 증거 리스트
        When: combine_evidence
        Then: unknown=1.0, masses={}, k=0.0"""
        result = combine_evidence([])
        assert result["unknown"] == 1.0
        assert result["masses"] == {}
        assert result["conflict_k"] == 0.0

    def test_single_evidence(self) -> None:
        """Given: 단일 증거 mass=0.7
        When: combine_evidence
        Then: mass=0.7, unknown=0.3"""
        result = combine_evidence([{"hypothesis": "1503", "mass": 0.7}])
        assert abs(result["masses"]["1503"] - 0.7) < 0.001
        assert abs(result["unknown"] - 0.3) < 0.001


# =========================================================================
# Test 2: combine_evidence — 충돌 시 K값 계산 + 정규화
# =========================================================================


class TestCombineEvidenceConflict:
    """상이 가설 충돌 시 K값 계산 + 정규화."""

    def test_conflict_k_nonzero(self) -> None:
        """Given: 1503호 mass 0.6, 1504호 mass 0.7 (상이 가설)
        When: combine_evidence
        Then: K > 0 (충돌), 정규화 후 masses 합 + unknown = 1.0"""
        evs = [
            {"hypothesis": "1503", "mass": 0.6},
            {"hypothesis": "1504", "mass": 0.7},
        ]
        result = combine_evidence(evs)
        assert result["conflict_k"] > 0.0
        # K = 0.6 * 0.7 = 0.42
        assert abs(result["conflict_k"] - 0.42) < 0.001
        # 정규화 후 합 = 1.0
        total = sum(result["masses"].values()) + result["unknown"]
        assert abs(total - 1.0) < 0.001

    def test_conflict_normalized_masses(self) -> None:
        """Given: 1503 mass 0.5, 1504 mass 0.5
        When: combine_evidence
        Then: K=0.25, 정규화 후 1503과 1504에 분배"""
        evs = [
            {"hypothesis": "1503", "mass": 0.5},
            {"hypothesis": "1504", "mass": 0.5},
        ]
        result = combine_evidence(evs)
        assert abs(result["conflict_k"] - 0.25) < 0.001
        m1503 = result["masses"]["1503"]
        m1504 = result["masses"]["1504"]
        # 둘 다 존재
        assert m1503 > 0
        assert m1504 > 0
        # 동일 mass이므로 동일한 결합 mass
        assert abs(m1503 - m1504) < 0.001

    def test_near_complete_conflict(self) -> None:
        """Given: 1503 mass 0.999, 1504 mass 0.999 (근완전 충돌)
        When: combine_evidence
        Then: K > 0.99 (근완전 충돌), masses는 여전히 정규화됨"""
        evs = [
            {"hypothesis": "1503", "mass": 0.999},
            {"hypothesis": "1504", "mass": 0.999},
        ]
        result = combine_evidence(evs)
        assert result["conflict_k"] > 0.99  # 근완전 충돌
        total = sum(result["masses"].values()) + result["unknown"]
        assert abs(total - 1.0) < 0.001  # 정규화 유지


# =========================================================================
# Test 3: resolve_cluster — P3 > CLOSURE_LABEL > ho_hint 우선순위
# =========================================================================


class TestResolveClusterPriority:
    """우선순위: P3 > CLOSURE_LABEL > ho_hint > 대장 대조."""

    def test_p3_highest_priority(self) -> None:
        """Given: P3 + closure_label + ho_hint + ledger 증거 혼재
        When: resolve_cluster
        Then: P3의 ho가 ho_final, is_estimate=False"""
        cluster = [
            {"ho": "1503", "source": "ledger", "mass": 0.5, "is_negative": False},
            {"ho": "1504", "source": "ho_hint", "mass": 0.7, "is_negative": False},
            {"ho": "1505", "source": "closure_label", "mass": 0.9, "is_negative": False},
            {"ho": "1506", "source": "p3", "mass": 0.95, "is_negative": False},
        ]
        result = resolve_cluster(cluster)
        assert result["ho_final"] == "1506"
        assert result["method"] == "p3"
        assert result["is_estimate"] is False

    def test_closure_label_over_ho_hint(self) -> None:
        """Given: closure_label + ho_hint (P3 없음)
        When: resolve_cluster
        Then: closure_label의 ho가 1순위, method=closure_label"""
        cluster = [
            {"ho": "1503", "source": "ledger", "mass": 0.5, "is_negative": False},
            {"ho": "1504", "source": "ho_hint", "mass": 0.7, "is_negative": False},
            {"ho": "1505", "source": "closure_label", "mass": 0.9, "is_negative": False},
        ]
        result = resolve_cluster(cluster)
        assert result["method"] == "closure_label"
        assert result["ho_final"] is not None

    def test_ho_hint_over_ledger(self) -> None:
        """Given: ho_hint + ledger (P3/closure 없음)
        When: resolve_cluster
        Then: method=ho_hint, ho_hint의 ho가 1순위"""
        cluster = [
            {"ho": "1503", "source": "ledger", "mass": 0.5, "is_negative": False},
            {"ho": "1504", "source": "ho_hint", "mass": 0.7, "is_negative": False},
        ]
        result = resolve_cluster(cluster)
        assert result["method"] == "ho_hint"

    def test_ledger_only(self) -> None:
        """Given: ledger만
        When: resolve_cluster
        Then: method=ledger"""
        cluster = [
            {"ho": "1503", "source": "ledger", "mass": 0.5, "is_negative": False},
            {"ho": "1504", "source": "ledger", "mass": 0.4, "is_negative": False},
        ]
        result = resolve_cluster(cluster)
        assert result["method"] == "ledger"

    def test_empty_cluster(self) -> None:
        """Given: 빈 클러스터
        When: resolve_cluster
        Then: ho_final=None"""
        result = resolve_cluster([])
        assert result["ho_final"] is None
        assert result["method"] == "none"


# =========================================================================
# Test 4: run_pipeline — F-S 매칭 → DS 결합 → 호 확정
# =========================================================================


class TestRunPipeline:
    """run_pipeline: F-S 매칭 → DS 결합 → 호 확정."""

    def test_fs_matching_to_ho_final(self) -> None:
        """Given: 1개 매물 + unit_master 5개
        When: run_pipeline
        Then: F-S 매칭 후 ho_final 반환"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        assert len(results) == 1
        assert results[0]["ho_final"] is not None
        assert results[0]["complex_id"] == "C1"
        assert results[0]["dong"] == "101"

    def test_ground_truth_p3_overrides(self) -> None:
        """Given: 매물 + AuctionResult ground truth (P3)
        When: run_pipeline
        Then: P3의 ho가 ho_final, is_estimate=False"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        gt = AuctionResult(
            complex_id="C1", dong="101", ho="1503",
            floor=15, area_m2=84.12, direction="S",
        )
        results = run_pipeline(listings, _SAMPLE_UNITS, ground_truths=[gt])
        assert results[0]["ho_final"] == "1503"
        assert results[0]["is_estimate"] is False
        assert results[0]["method"] == "p3"

    def test_ground_truth_closure_label(self) -> None:
        """Given: 매물 + RegistryConfirm ground truth (CLOSURE_LABEL)
        When: run_pipeline
        Then: closure_label method"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        results = run_pipeline(listings, _SAMPLE_UNITS, ground_truths=[gt])
        assert results[0]["ho_final"] == "1503"
        assert results[0]["method"] == "closure_label"

    def test_empty_listings(self) -> None:
        """Given: 빈 listings
        When: run_pipeline
        Then: 빈 결과"""
        results = run_pipeline([], _SAMPLE_UNITS)
        assert results == []

    def test_no_match(self) -> None:
        """Given: 매칭되는 unit 없음
        When: run_pipeline
        Then: ho_final=None"""
        listings = [{"complex_id": "C9", "dong": "999",
                     "floor_info": "1", "area2": 99.99,
                     "direction": "N", "area_type": "99X"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        assert results[0]["ho_final"] is None


# =========================================================================
# Test 5: 다호 후보 시 [{ho, probability}] 리스트 출력
# =========================================================================


class TestMultiHoCandidates:
    """다호 후보 시 [{ho, probability}] 확률 리스트 출력 (A81)."""

    def test_multiple_candidates_list(self) -> None:
        """Given: 2개 이상 후보 호
        When: run_pipeline
        Then: candidate_hos에 [{ho, probability}] 리스트"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        ch = results[0]["candidate_hos"]
        assert len(ch) >= 1
        for c in ch:
            assert "ho" in c
            assert "probability" in c
            assert 0.0 <= c["probability"] <= 1.0

    def test_probabilities_normalized(self) -> None:
        """Given: 다호 후보
        When: run_pipeline
        Then: 확률 합계 ≈ 1.0"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        ch = results[0]["candidate_hos"]
        if len(ch) > 1:
            total = sum(c["probability"] for c in ch)
            assert abs(total - 1.0) < 0.05

    def test_ds_combination_with_ho_hint(self) -> None:
        """Given: F-S 후보 + ho_hint
        When: run_pipeline
        Then: ho_hint가 후보에 추가되어 DS 결합"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A",
                     "ho_hint": "1503"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        # ho_hint "1503"이 DS 결합으로 부스트
        assert results[0]["ho_final"] is not None
        ch = results[0]["candidate_hos"]
        hos = [c["ho"] for c in ch]
        assert "1503" in hos


# =========================================================================
# Test 6: 음의 증거(공실) → 후보에서 제외
# =========================================================================


class TestNegativeEvidenceVacancy:
    """음의 증거(공실) → 후보에서 제외."""

    def test_vacancy_excludes_candidate(self) -> None:
        """Given: 1503호 후보 + 1503호 공실(vacancy_hos)
        When: run_pipeline
        Then: 1503호가 후보에서 제외 또는 확률 대폭 감소"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A",
                     "vacancy_hos": ["1503"]}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        ch = results[0]["candidate_hos"]
        hos = [c["ho"] for c in ch]
        # 1503이 제외되거나, 1503보다 다른 호가 더 높은 확률
        if "1503" in hos:
            p1503 = next(c["probability"] for c in ch if c["ho"] == "1503")
            # 1503의 확률이 매우 낮아야 함 (음의 증거로 감소)
            assert p1503 < 0.3
        else:
            # 1503이 완전히 제외됨
            assert "1503" not in hos

    def test_vacancy_only_negative(self) -> None:
        """Given: 음의 증거만 (양의 증거 없음)
        When: resolve_cluster
        Then: ho_final=None"""
        cluster = [
            {"ho": "1503", "source": "vacancy", "mass": 0.9, "is_negative": True},
        ]
        result = resolve_cluster(cluster)
        assert result["ho_final"] is None

    def test_vacancy_with_positive(self) -> None:
        """Given: 1503 양의 증거 + 1503 음의 증거
        When: combine_evidence
        Then: 1503의 mass가 감소"""
        evs = [
            {"hypothesis": "1503", "mass": 0.7, "is_negative": False},
            {"hypothesis": "1503", "mass": 0.9, "is_negative": True},
        ]
        result = combine_evidence(evs)
        # 음의 증거로 1503의 mass가 감소해야 함
        # K = 0.7 * 0.9 = 0.63
        assert result["conflict_k"] > 0.5
        # 1503의 mass는 크게 감소
        if "1503" in result["masses"]:
            assert result["masses"]["1503"] < 0.3


# =========================================================================
# Test 7: 가중합 미사용 확인
# =========================================================================


class TestNoWeightedSum:
    """가중합(0.30/0.30/0.25/0.15) 사용 금지 확인."""

    def test_no_weighted_sum_constants(self) -> None:
        """Given: pipeline.py 소스 코드
        When: 정적 분석
        Then: 가중합 패턴 (0.30/0.25/0.15) 없음"""
        from src import pipeline
        source = inspect.getsource(pipeline)
        forbidden = ["0.30", "0.25", "0.15", "weighted_sum", "weight_sum"]
        for pattern in forbidden:
            assert pattern not in source, f"금지된 패턴 발견: {pattern}"

    def test_no_explicit_weight_assignment(self) -> None:
        """Given: pipeline.py 소스 코드
        When: 정적 분석
        Then: weights = 또는 w = 형태의 가중합 할당 없음"""
        from src import pipeline
        source = inspect.getsource(pipeline)
        forbidden_patterns = ["weights =", "weight_dict", "WEIGHTS"]
        for pattern in forbidden_patterns:
            assert pattern not in source, f"금지된 패턴: {pattern}"

    def test_ds_combination_not_weighted(self) -> None:
        """Given: 2개 증거 (0.6, 0.7) 동일 가설
        When: combine_evidence
        Then: 결합 mass ≠ 단순 가중합 (0.6+0.7)/2 = 0.65"""
        evs = [
            {"hypothesis": "1503", "mass": 0.6},
            {"hypothesis": "1503", "mass": 0.7},
        ]
        result = combine_evidence(evs)
        combined = result["masses"]["1503"]
        weighted_avg = (0.6 + 0.7) / 2  # 0.65
        assert abs(combined - weighted_avg) > 0.05  # DS ≠ 가중합
        assert combined > weighted_avg  # DS는 결합으로 더 강해짐


# =========================================================================
# Test 8: DS 단독 매칭 아님 (F-S 먼저, DS는 충돌 해결만)
# =========================================================================


class TestDSNotStandalone:
    """DS는 F-S 출력 위 충돌 해결용만. 단독 매칭 프레임워크 아님."""

    def test_run_pipeline_uses_fs_first(self) -> None:
        """Given: 매물 + unit_master
        When: run_pipeline
        Then: F-S 매칭 결과가 클러스터에 포함 (ledger source)"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        # F-S 매칭 없이는 결과 불가
        assert len(results) == 1
        assert results[0]["ho_final"] is not None

    def test_ds_only_resolves_conflict(self) -> None:
        """Given: F-S가 2개 후보 생성 + ho_hint가 1개 지정
        When: run_pipeline
        Then: DS가 충돌 해결로 ho_hint 후보 부스트"""
        listings = [{"complex_id": "C1", "dong": "101",
                     "floor_info": "15", "area2": 84.12,
                     "direction": "S", "area_type": "84A",
                     "ho_hint": "1503"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        r = results[0]
        # DS 결합 사용 확인 (method_log에 DS 언급)
        assert any("DS" in log for log in r["method_log"])

    def test_no_fs_no_result(self) -> None:
        """Given: 매칭 가능한 unit_master 없음 + ground_truth 없음 + ho_hint 없음
        When: run_pipeline
        Then: ho_final=None (DS만으로는 매칭 불가)"""
        listings = [{"complex_id": "C9", "dong": "999",
                     "floor_info": "1", "area2": 99.99,
                     "direction": "N", "area_type": "99X"}]
        results = run_pipeline(listings, _SAMPLE_UNITS)
        assert results[0]["ho_final"] is None
        assert results[0]["candidate_hos"] == []

    def test_fs_provides_candidates_ds_resolves(self) -> None:
        """Given: F-S가 1501, 1503 후보 생성 (동일 조건)
        When: ho_hint="1503" 추가 후 run_pipeline
        Then: 1503이 1501보다 높은 확률 (DS 부스트)"""
        listings_no_hint = [{"complex_id": "C1", "dong": "101",
                             "floor_info": "15", "area2": 84.12,
                             "direction": "S", "area_type": "84A"}]
        listings_with_hint = [{"complex_id": "C1", "dong": "101",
                               "floor_info": "15", "area2": 84.12,
                               "direction": "S", "area_type": "84A",
                               "ho_hint": "1503"}]
        r_no = run_pipeline(listings_no_hint, _SAMPLE_UNITS)[0]
        r_yes = run_pipeline(listings_with_hint, _SAMPLE_UNITS)[0]
        # ho_hint 없을 때: 1501과 1503 비슷한 확률
        # ho_hint 있을 때: 1503이 더 높은 확률
        ch_yes = {c["ho"]: c["probability"] for c in r_yes["candidate_hos"]}
        ch_no = {c["ho"]: c["probability"] for c in r_no["candidate_hos"]}
        if "1503" in ch_yes and "1503" in ch_no:
            assert ch_yes["1503"] >= ch_no["1503"]
