"""match_units RPC + matcher 클라이언트 테스트 (Todo 21)."""

from __future__ import annotations

import pytest

from src.matcher import match_ho


# Mock unit_master data
_UNIT_MASTER = [
    {
        "canonical_ho_id": "1503", "complex_id": "C1", "dong": "101",
        "ho": "1503", "floor": 15, "area_exclusive": 8400,
        "area_type": "84A", "direction": "S", "public_price": 120000,
    },
    {
        "canonical_ho_id": "1504", "complex_id": "C1", "dong": "101",
        "ho": "1504", "floor": 15, "area_exclusive": 11500,
        "area_type": "115A", "direction": "S", "public_price": 150000,
    },
    {
        "canonical_ho_id": "1603", "complex_id": "C1", "dong": "101",
        "ho": "1603", "floor": 16, "area_exclusive": 8400,
        "area_type": "84B", "direction": "N", "public_price": 125000,
    },
    {
        "canonical_ho_id": "2001", "complex_id": "C2", "dong": "102",
        "ho": "2001", "floor": 20, "area_exclusive": 8400,
        "area_type": "84A", "direction": "S", "public_price": 130000,
    },
]


class TestMatchHo:
    def test_exact_match(self):
        """정확 매칭: complex_id + area_cm2 + area_type + direction."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8400, area_type="84A", direction="S",
        )
        assert len(results) == 1
        assert results[0]["ho"] == "1503"
        assert results[0]["score"] > 0

    def test_multiple_candidates(self):
        """다수 후보: area_cm2만 일치 → 여러 호."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8400,
        )
        assert len(results) == 2  # 1503, 1603
        ho_list = [r["ho"] for r in results]
        assert "1503" in ho_list
        assert "1603" in ho_list

    def test_dong_filter(self):
        """동 필터: dong="101"."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", dong="101", area_cm2=8400,
        )
        assert len(results) == 2
        for r in results:
            assert r["dong"] == "101"

    def test_different_complex(self):
        """다른 complex_id → 매칭 없음."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C99", area_cm2=8400,
        )
        assert len(results) == 0

    def test_floor_range(self):
        """층 범위 필터: floor_min=15, floor_max=16."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8400, floor_min=15, floor_max=16,
        )
        for r in results:
            assert 15 <= r["floor"] <= 16

    def test_area_tolerance(self):
        """면적 ±500cm² tolerance."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8450,  # within 500 of 8400
        )
        assert len(results) >= 1

    def test_probabilities(self):
        """다호 후보 → probability 계산 (A81)."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8400,
        )
        assert len(results) >= 1
        total_prob = sum(r["probability"] for r in results)
        assert abs(total_prob - 1.0) < 0.001

    def test_score_ordering(self):
        """score 높은 순 정렬."""
        results = match_ho(
            [], _UNIT_MASTER,
            complex_id="C1", area_cm2=8400, direction="S",
        )
        for i in range(len(results) - 1):
            assert results[i]["score"] >= results[i + 1]["score"]

    def test_empty_unit_master(self):
        """unit_master가 비어있으면 빈 리스트."""
        results = match_ho([], [], complex_id="C1", area_cm2=8400)
        assert results == []
