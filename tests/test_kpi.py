"""KPI 지표 단위 테스트."""
from __future__ import annotations

import pytest

from src.domain import HoConclusion
from src.kpi import (
    compute_demand_weighted_solved,
    compute_multi_prob_rate,
    compute_precision_at_1,
    compute_single_confirm_coverage,
    generate_kpi_dashboard,
)


def _make_conclusion(
    complex_id: str = "c1",
    dong: str = "101동",
    candidate_hos: list | None = None,
    ho_final: str | None = None,
    grade: str = "medium",
    is_estimate: bool = True,
) -> HoConclusion:
    # candidate_hos 가 None 이면 기본값, 빈 리스트 [] 도 그대로 사용
    hos: list = (
        [{"ho": "101호", "probability": 1.0}]
        if candidate_hos is None
        else candidate_hos
    )
    return HoConclusion(
        complex_id=complex_id,
        dong=dong,
        candidate_hos=hos,
        ho_final=ho_final,
        grade=grade,
        is_estimate=is_estimate,
    )


class TestComputePrecisionAt1:
    """compute_precision_at_1 — 최고 확률 후보 정답 일치율."""

    def test_all_correct(self) -> None:
        """Given 모든 결론 정답 When P@1 계산 Then 1.0"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                dong="101동",
                candidate_hos=[{"ho": "101호", "probability": 0.95}],
            ),
            _make_conclusion(
                complex_id="c1",
                dong="102동",
                candidate_hos=[{"ho": "201호", "probability": 0.90}],
            ),
        ]
        labels = [
            {"complex_id": "c1", "dong": "101동", "ho": "101호"},
            {"complex_id": "c1", "dong": "102동", "ho": "201호"},
        ]
        result = compute_precision_at_1(conclusions, labels)
        assert result == 1.0

    def test_half_correct(self) -> None:
        """Given 절반 정답 When P@1 계산 Then 0.5"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                dong="101동",
                candidate_hos=[{"ho": "101호", "probability": 0.95}],
            ),
            _make_conclusion(
                complex_id="c1",
                dong="102동",
                candidate_hos=[{"ho": "999호", "probability": 0.90}],
            ),
        ]
        labels = [
            {"complex_id": "c1", "dong": "101동", "ho": "101호"},
            {"complex_id": "c1", "dong": "102동", "ho": "201호"},
        ]
        result = compute_precision_at_1(conclusions, labels)
        assert result == 0.5

    def test_no_labels_returns_zero(self) -> None:
        """Given 라벨 없음 When P@1 계산 Then 0.0"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
        ]
        result = compute_precision_at_1(conclusions, [])
        assert result == 0.0

    def test_no_conclusions_returns_zero(self) -> None:
        """Given 결론 없음 When P@1 계산 Then 0.0"""
        result = compute_precision_at_1([], [{"complex_id": "c1", "dong": "101동", "ho": "101호"}])
        assert result == 0.0

    def test_some_not_labeled_ignored(self) -> None:
        """Given 일부만 라벨 있음 When P@1 계산 Then 라벨 있는 것만 계산"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
            _make_conclusion(
                complex_id="c1",
                dong="102동",
                candidate_hos=[{"ho": "201호", "probability": 0.90}],
            ),
        ]
        labels = [
            {"complex_id": "c1", "dong": "102동", "ho": "201호"},
        ]
        result = compute_precision_at_1(conclusions, labels)
        assert result == 1.0  # only 102동 is labeled and it's correct


class TestComputeSingleConfirmCoverage:
    """compute_single_confirm_coverage — 단일확정 커버리지."""

    def test_all_single(self) -> None:
        """Given 모든 결론 단일 후보 When 단일확정 계산 Then 1.0"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
            _make_conclusion(candidate_hos=[{"ho": "102호"}]),
        ]
        assert compute_single_confirm_coverage(conclusions) == 1.0

    def test_mixed(self) -> None:
        """Given 혼합 When 단일확정 계산 Then 0.5"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
            _make_conclusion(
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
            ),
        ]
        assert compute_single_confirm_coverage(conclusions) == 0.5

    def test_none_single(self) -> None:
        """Given 단일 후보 없음 When 단일확정 계산 Then 0.0"""
        conclusions = [
            _make_conclusion(
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
            ),
        ]
        assert compute_single_confirm_coverage(conclusions) == 0.0

    def test_empty_list(self) -> None:
        """Given 빈 리스트 When 단일확정 계산 Then 0.0"""
        assert compute_single_confirm_coverage([]) == 0.0


class TestComputeMultiProbRate:
    """compute_multi_prob_rate — 다호확률리스트 출력률."""

    def test_all_multi(self) -> None:
        """Given 모든 결론 다호 When 다호율 계산 Then 1.0"""
        conclusions = [
            _make_conclusion(
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
            ),
            _make_conclusion(
                candidate_hos=[{"ho": "201호"}, {"ho": "202호"}],
            ),
        ]
        assert compute_multi_prob_rate(conclusions) == 1.0

    def test_mixed(self) -> None:
        """Given 혼합 When 다호율 계산 Then 0.5"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
            _make_conclusion(
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
            ),
        ]
        assert compute_multi_prob_rate(conclusions) == 0.5

    def test_none_multi(self) -> None:
        """Given 다호 없음 When 다호율 계산 Then 0.0"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
        ]
        assert compute_multi_prob_rate(conclusions) == 0.0

    def test_empty_list(self) -> None:
        """Given 빈 리스트 When 다호율 계산 Then 0.0"""
        assert compute_multi_prob_rate([]) == 0.0


class TestComputeDemandWeightedSolved:
    """compute_demand_weighted_solved — 수요가중 solved율."""

    def test_all_solved(self) -> None:
        """Given 모든 결론 solved + 균등 가중치 When 계산 Then 1.0"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
            _make_conclusion(candidate_hos=[{"ho": "102호"}]),
        ]
        demand = {"c1": 10.0}
        assert compute_demand_weighted_solved(conclusions, demand) == 1.0

    def test_half_solved_with_weight(self) -> None:
        """Given 절반 solved + 가중치 When 계산 Then 가중 solved율"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                candidate_hos=[{"ho": "101호"}],
            ),
            _make_conclusion(
                complex_id="c2",
                candidate_hos=[],  # unsolved
            ),
        ]
        demand = {"c1": 10.0, "c2": 10.0}
        result = compute_demand_weighted_solved(conclusions, demand)
        assert result == 0.5

    def test_weighted_different(self) -> None:
        """Given solved 여부 + 다른 가중치 When 계산 Then 가중 반영"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                candidate_hos=[{"ho": "101호"}],  # solved, weight=90
            ),
            _make_conclusion(
                complex_id="c2",
                candidate_hos=[],  # unsolved, weight=10
            ),
        ]
        demand = {"c1": 90.0, "c2": 10.0}
        result = compute_demand_weighted_solved(conclusions, demand)
        assert result == 0.9  # 90/(90+10)

    def test_no_demand_returns_zero(self) -> None:
        """Given demand 없음 When 계산 Then 0.0"""
        conclusions = [
            _make_conclusion(candidate_hos=[{"ho": "101호"}]),
        ]
        assert compute_demand_weighted_solved(conclusions, {}) == 0.0

    def test_zero_weight_ignored(self) -> None:
        """Given 가중치 0 When 계산 Then 해당 결론 제외"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                candidate_hos=[{"ho": "101호"}],
            ),
            _make_conclusion(
                complex_id="c2",
                candidate_hos=[],  # unsolved
            ),
        ]
        demand = {"c1": 0.0, "c2": 10.0}
        result = compute_demand_weighted_solved(conclusions, demand)
        # c1 is solved but weight is 0 → ignored
        # c2 is unsolved with weight 10 → total_weight=10, no solved
        assert result == 0.0

    def test_empty_conclusions(self) -> None:
        """Given 빈 결론 When 계산 Then 0.0"""
        assert compute_demand_weighted_solved([], {"c1": 10.0}) == 0.0


class TestGenerateKpiDashboard:
    """generate_kpi_dashboard — 전체 KPI 대시보드."""

    def test_returns_all_keys(self) -> None:
        """Given 기본 데이터 When 대시보드 생성 Then 모든 예상 키 포함"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                dong="101동",
                candidate_hos=[{"ho": "101호"}],
                grade="high",
            ),
            _make_conclusion(
                complex_id="c2",
                dong="102동",
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
                grade="medium",
            ),
        ]
        labels = [{"complex_id": "c1", "dong": "101동", "ho": "101호"}]
        demand = {"c1": 10.0, "c2": 5.0}
        dashboard = generate_kpi_dashboard(conclusions, labels, demand)

        expected_keys = {
            "total_conclusions",
            "complex_ids",
            "grade_counts",
            "precision_at_1",
            "single_confirm_coverage",
            "multi_prob_rate",
            "demand_weighted_solved",
            "labeled_count",
        }
        assert set(dashboard.keys()) == expected_keys

    def test_values_are_correct(self) -> None:
        """Given 제어된 입력 When 대시보드 생성 Then 각 KPI 정확"""
        conclusions = [
            _make_conclusion(
                complex_id="c1",
                dong="101동",
                candidate_hos=[{"ho": "101호"}],
                grade="high",
            ),
            _make_conclusion(
                complex_id="c1",
                dong="102동",
                candidate_hos=[{"ho": "101호"}, {"ho": "102호"}],
                grade="medium",
            ),
            _make_conclusion(
                complex_id="c2",
                dong="201동",
                candidate_hos=[],  # unsolved
                grade="none",
            ),
        ]
        labels = [
            {"complex_id": "c1", "dong": "101동", "ho": "101호"},  # correct
            {"complex_id": "c1", "dong": "102동", "ho": "102호"},  # top cand wrong
        ]
        demand = {"c1": 10.0, "c2": 0.0}
        dashboard = generate_kpi_dashboard(conclusions, labels, demand)

        assert dashboard["total_conclusions"] == 3
        assert dashboard["complex_ids"] == ["c1", "c2"]
        assert dashboard["grade_counts"] == {"high": 1, "medium": 1, "none": 1}
        assert dashboard["precision_at_1"] == pytest.approx(0.5, abs=0.001)
        assert dashboard["single_confirm_coverage"] == pytest.approx(1 / 3, abs=0.001)
        assert dashboard["multi_prob_rate"] == pytest.approx(1 / 3, abs=0.001)
        assert dashboard["demand_weighted_solved"] == pytest.approx(1.0, abs=0.001)
        assert dashboard["labeled_count"] == 2
