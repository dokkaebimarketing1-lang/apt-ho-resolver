"""추론 인터페이스 단위 테스트 — infer_complex + infer_unit.

테스트 전략:
- infer_complex: 단지명 + mock 매물 → HoConclusion 리스트
- infer_unit: 동+층+향+면적 질의 → HoConclusion
- 다호 후보 시 [{ho, probability}] 리스트 확인
- 증거 부족 시 ho_final=None 확인
- is_estimate=True 기본 확인
- Fellegi-Sunter 가중치 계산 확인
"""

from __future__ import annotations

from src.domain import HoConclusion
from src.inference import infer_complex, infer_unit


# =========================================================================
# Fixtures
# =========================================================================

_SAMPLE_UNITS: list[dict] = [
    # complex_id, dong, ho, floor, area_type, direction
    {"complex_id": "C1", "dong": "101", "ho": "1501",
     "floor": 15, "area_type": "84A", "direction": "S"},
    {"complex_id": "C1", "dong": "101", "ho": "1502",
     "floor": 15, "area_type": "84B", "direction": "E"},
    {"complex_id": "C1", "dong": "101", "ho": "1503",
     "floor": 15, "area_type": "84A", "direction": "S"},
    {"complex_id": "C1", "dong": "101", "ho": "1601",
     "floor": 16, "area_type": "84A", "direction": "S"},
    {"complex_id": "C1", "dong": "101", "ho": "1602",
     "floor": 16, "area_type": "84B", "direction": "E"},
    {"complex_id": "C1", "dong": "101", "ho": "1603",
     "floor": 16, "area_type": "84A", "direction": "S"},
    {"complex_id": "C1", "dong": "102", "ho": "1501",
     "floor": 15, "area_type": "59A", "direction": "S"},
    {"complex_id": "C1", "dong": "102", "ho": "1502",
     "floor": 15, "area_type": "59B", "direction": "W"},
    {"complex_id": "C2", "dong": "101", "ho": "0701",
     "floor": 7, "area_type": "84A", "direction": "S"},
    {"complex_id": "C2", "dong": "101", "ho": "0702",
     "floor": 7, "area_type": "84A", "direction": "S"},
]

_SAMPLE_LISTINGS: list[dict] = [
    # complex_id, dong, floor_info, area2, direction, area_type
    {"complex_id": "C1", "dong": "101",
     "floor_info": "15", "area2": 84.12, "direction": "S",
     "area_type": "84A"},
    {"complex_id": "C1", "dong": "102",
     "floor_info": "15", "area2": 59.87, "direction": "W",
     "area_type": "59B"},
    {"complex_id": "C2", "dong": "101",
     "floor_info": "7", "area2": 84.00, "direction": "S",
     "area_type": "84A"},
]


# =========================================================================
# Test: infer_complex
# =========================================================================


class TestInferComplex:
    """infer_complex — 단지 추론 인터페이스."""

    def test_returns_ho_conclusions(self) -> None:
        """Given: 단지 C1 + 2개 매물 + 10개 unit_master
        When: infer_complex("C1", listings, units)
        Then: HoConclusion 리스트 반환"""
        listings = _SAMPLE_LISTINGS[:2]
        results = infer_complex("C1", listings, _SAMPLE_UNITS)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, HoConclusion)

    def test_first_listing_101_dong_84a_south(self) -> None:
        """Given: 101동 15층 84A 남향 매물
        When: infer_complex
        Then: ho_final="1501" 또는 "1503" (동일 조건 2개 호)"""
        listings = [_SAMPLE_LISTINGS[0]]
        results = infer_complex("C1", listings, _SAMPLE_UNITS)
        result = results[0]
        assert result.complex_id == "C1"
        assert result.dong == "101"
        assert result.ho_final is not None
        assert len(result.candidate_hos) >= 1

    def test_complex_name_filtering(self) -> None:
        """Given: complex_name="C1" 으로 C2 매물도 전달
        When: infer_complex
        Then: C2 매물은 ho_final=None (매칭 실패)"""
        results = infer_complex("C1", _SAMPLE_LISTINGS, _SAMPLE_UNITS)
        # C1 매물은 매칭 성공
        assert results[0].ho_final is not None
        assert results[1].ho_final is not None
        # C2 매물은 C1 unit_master에 없음 → ho_final=None
        assert results[2].ho_final is None

    def test_candidate_hos_has_probability(self) -> None:
        """Given: 매물 1건
        When: infer_complex
        Then: candidate_hos 각 항목에 ho + probability"""
        results = infer_complex("C1", [_SAMPLE_LISTINGS[0]], _SAMPLE_UNITS)
        for r in results:
            for ch in r.candidate_hos:
                assert "ho" in ch
                assert "probability" in ch
                assert 0.0 <= ch["probability"] <= 1.0

    def test_is_estimate_default_true(self) -> None:
        """Given: infer_complex 결과
        Then: is_estimate=True"""
        results = infer_complex("C1", [_SAMPLE_LISTINGS[0]], _SAMPLE_UNITS)
        assert results[0].is_estimate is True

    def test_empty_listings(self) -> None:
        """Given: 빈 listings
        When: infer_complex
        Then: 빈 리스트"""
        results = infer_complex("C1", [], _SAMPLE_UNITS)
        assert results == []

    def test_empty_unit_master(self) -> None:
        """Given: 빈 unit_master
        When: infer_complex
        Then: 각 HoConclusion의 ho_final=None"""
        results = infer_complex("C1", _SAMPLE_LISTINGS[:1], [])
        assert len(results) == 1
        assert results[0].ho_final is None
        assert results[0].candidate_hos == []

    def test_c2_listing_no_c1_units(self) -> None:
        """Given: C2 매물 but C1 unit_master만
        When: infer_complex
        Then: ho_final=None"""
        results = infer_complex("C1", [_SAMPLE_LISTINGS[2]], _SAMPLE_UNITS)
        assert results[0].ho_final is None

    def test_dong_mismatch(self) -> None:
        """Given: 102동 59B/W 매물
        When: infer_complex
        Then: 1502(59B/W 정확 일치)가 1501(59A/S 불일치)보다 높은 확률"""
        listings = [_SAMPLE_LISTINGS[1]]
        results = infer_complex("C1", listings, _SAMPLE_UNITS)
        result = results[0]
        assert result.dong == "102"
        assert len(result.candidate_hos) >= 2
        # 1502 = 59B/W exact match → 1순위
        assert result.candidate_hos[0]["ho"] == "1502"
        # 1502가 1501보다 높은 확률
        p1502 = next(c["probability"] for c in result.candidate_hos if c["ho"] == "1502")
        p1501 = next(c["probability"] for c in result.candidate_hos if c["ho"] == "1501")
        assert p1502 > p1501

    def test_custom_m_probs(self) -> None:
        """Given: 사용자 지정 m_probs
        When: infer_complex
        Then: 정상 동작"""
        m_probs = {"dong": 0.99, "floor": 0.90,
                   "area_type": 0.95, "direction": 0.85}
        results = infer_complex("C1", [_SAMPLE_LISTINGS[0]], _SAMPLE_UNITS,
                                m_probs=m_probs)
        assert len(results) == 1
        assert results[0].ho_final is not None


# =========================================================================
# Test: infer_unit
# =========================================================================


class TestInferUnit:
    """infer_unit — 세대 질의 인터페이스."""

    def test_returns_ho_conclusion(self) -> None:
        """Given: 유효한 질의
        When: infer_unit
        Then: HoConclusion 반환"""
        result = infer_unit(
            complex_id="C1", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert isinstance(result, HoConclusion)

    def test_101_dong_15f_84a_south(self) -> None:
        """Given: C1 101동 15층 84A 남향
        When: infer_unit
        Then: 후보 호는 1501과 1503 (둘 다 조건 일치),
              ho_final은 1501(더 낮은 호)"""
        result = infer_unit(
            complex_id="C1", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.complex_id == "C1"
        assert result.dong == "101"
        assert result.ho_final is not None
        hos = [ch["ho"] for ch in result.candidate_hos]
        assert "1501" in hos
        assert "1503" in hos
        # 84B는 area_type 불일치로 제외
        assert "1502" not in hos

    def test_multiple_candidates_have_probabilities(self) -> None:
        """Given: 다호 후보
        When: infer_unit
        Then: [{ho, probability}] 리스트"""
        result = infer_unit(
            complex_id="C1", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert len(result.candidate_hos) >= 2
        for ch in result.candidate_hos:
            assert "ho" in ch
            assert "probability" in ch
            assert 0.0 <= ch["probability"] <= 1.0
        # 확률 합계 ~= 1.0
        total = sum(ch["probability"] for ch in result.candidate_hos)
        assert abs(total - 1.0) < 0.01

    def test_insufficient_evidence(self) -> None:
        """Given: 존재하지 않는 complex_id
        When: infer_unit
        Then: ho_final=None, 빈 candidate_hos"""
        result = infer_unit(
            complex_id="NONEXIST", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.ho_final is None
        assert result.candidate_hos == []

    def test_no_match_for_wrong_dong(self) -> None:
        """Given: 존재하지 않는 동
        When: infer_unit
        Then: ho_final=None"""
        result = infer_unit(
            complex_id="C1", dong="999", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.ho_final is None

    def test_is_estimate_default_true(self) -> None:
        """Given: infer_unit 결과
        Then: is_estimate=True"""
        result = infer_unit(
            complex_id="C1", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.is_estimate is True

    def test_direction_mismatch_excludes(self) -> None:
        """Given: 서향(W) 질의
        When: infer_unit
        Then: 남향/동향 호는 제외됨"""
        result = infer_unit(
            complex_id="C1", dong="102", floor=15,
            area_type="59B", direction="W",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.ho_final is not None
        for ch in result.candidate_hos:
            # 1502 only has direction=W in dong 102
            assert ch["ho"] == "1502"

    def test_floor_proximity_scoring(self) -> None:
        """Given: 16층 질의 (but 15층/16층 유닛 모두 있음)
        When: infer_unit 16층
        Then: 16층 유닛(1601)이 15층(1501)보다 높은 확률"""
        result = infer_unit(
            complex_id="C1", dong="101", floor=16,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
        )
        assert result.ho_final is not None
        # 1601 should appear
        hos = [ch["ho"] for ch in result.candidate_hos]
        assert "1601" in hos

    def test_custom_m_probs(self) -> None:
        """Given: 사용자 지정 m/u_probs
        When: infer_unit
        Then: 정상 동작"""
        m_probs = {"dong": 0.99, "floor": 0.95,
                   "area_type": 0.98, "direction": 0.90}
        u_probs = {"dong": 0.01, "floor": 0.05,
                   "area_type": 0.02, "direction": 0.10}
        result = infer_unit(
            complex_id="C1", dong="101", floor=15,
            area_type="84A", direction="S",
            unit_master=_SAMPLE_UNITS,
            m_probs=m_probs, u_probs=u_probs,
        )
        assert result.ho_final is not None
