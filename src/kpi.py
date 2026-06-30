"""KPI 지표 계산 — 정확도·커버리지·다호확률리스트·수요가중 solved율.

핵심 KPI:
- precision@1 (P@1): 가장 높은 확률의 후보가 정답과 일치하는 비율. 게이트: 95%.
- 단일확정 커버리지: candidate_hos 가 1개인 결론의 비율.
- 다호확률리스트 출력률: candidate_hos 가 2개 이상인 결론의 비율.
- 수요가중 solved율: 수요(매물량)로 가중치를 둔 solved 비율.
"""

from __future__ import annotations

from typing import Any

from src.domain import HoConclusion


def compute_precision_at_1(
    conclusions: list[HoConclusion],
    labels: list[dict[str, Any]],
) -> float:
    """precision@1 (P@1) — 최고 확률 후보의 정답 일치율.

    Args:
        conclusions: 최종 호 결론 리스트.
        labels: 정답 라벨 리스트. 각 항목은 {"complex_id": str, "dong": str, "ho": str}.

    Returns:
        0.0 ~ 1.0 사이의 정밀도. 라벨이 없으면 0.0.
    """
    if not conclusions or not labels:
        return 0.0

    # 라벨 인덱스 구축: (complex_id, dong) -> ho
    label_map: dict[tuple[str, str], str] = {}
    for lbl in labels:
        key = (lbl.get("complex_id", ""), lbl.get("dong", ""))
        label_map[key] = lbl.get("ho", "")

    correct = 0
    total_labeled = 0

    for c in conclusions:
        key = (c.complex_id, c.dong)
        expected = label_map.get(key)
        if expected is None:
            continue  # 이 결론은 라벨 없음 — KPI 계산에서 제외

        total_labeled += 1
        if c.candidate_hos and len(c.candidate_hos) > 0:
            top_candidate = c.candidate_hos[0].get("ho", "")
            if top_candidate == expected:
                correct += 1

    if total_labeled == 0:
        return 0.0

    return correct / total_labeled


def compute_single_confirm_coverage(
    conclusions: list[HoConclusion],
) -> float:
    """단일확정 커버리지 — candidate_hos 가 1개인 결론의 비율.

    Args:
        conclusions: 최종 호 결론 리스트.

    Returns:
        0.0 ~ 1.0 사이의 비율. 결론이 없으면 0.0.
    """
    if not conclusions:
        return 0.0

    single_count = sum(1 for c in conclusions if len(c.candidate_hos) == 1)
    return single_count / len(conclusions)


def compute_multi_prob_rate(
    conclusions: list[HoConclusion],
) -> float:
    """다호확률리스트 출력률 — candidate_hos 가 2개 이상인 결론의 비율.

    Args:
        conclusions: 최종 호 결론 리스트.

    Returns:
        0.0 ~ 1.0 사이의 비율. 결론이 없으면 0.0.
    """
    if not conclusions:
        return 0.0

    multi_count = sum(1 for c in conclusions if len(c.candidate_hos) >= 2)
    return multi_count / len(conclusions)


def compute_demand_weighted_solved(
    conclusions: list[HoConclusion],
    demand: dict[str, float],
) -> float:
    """수요가중 solved율 — 각 complex_id 의 매물량(수요)로 가중치를 둔 solved 비율.

    "solved" = candidate_hos 에 최소 1개의 후보가 있음 (ho_final 과 무관).
    수요가중 = sum(가중치 * solved) / sum(가중치).

    Args:
        conclusions: 최종 호 결론 리스트.
        demand: {complex_id: 가중치} 딕셔너리. 가중치는 양수여야 함.

    Returns:
        0.0 ~ 1.0 사이의 가중 solved율. 가중치가 없으면 0.0.
    """
    if not conclusions or not demand:
        return 0.0

    weighted_solved = 0.0
    total_weight = 0.0

    for c in conclusions:
        weight = demand.get(c.complex_id, 0.0)
        if weight <= 0:
            continue
        total_weight += weight
        if len(c.candidate_hos) >= 1:
            weighted_solved += weight

    if total_weight == 0.0:
        return 0.0

    return weighted_solved / total_weight


def generate_kpi_dashboard(
    conclusions: list[HoConclusion],
    labels: list[dict[str, Any]],
    demand: dict[str, float],
) -> dict[str, Any]:
    """KPI 대시보드 dict 생성 — 모든 핵심 KPI 를 한 번에 계산.

    Args:
        conclusions: 최종 호 결론 리스트.
        labels: 정답 라벨 리스트.
        demand: 수요 가중치 딕셔너리.

    Returns:
        {
            "total_conclusions": int,
            "complex_ids": list[str],
            "grade_counts": dict[str, int],
            "precision_at_1": float,
            "single_confirm_coverage": float,
            "multi_prob_rate": float,
            "demand_weighted_solved": float,
            "labeled_count": int,
        }
    """
    grade_counts: dict[str, int] = {}
    for c in conclusions:
        grade_counts[c.grade] = grade_counts.get(c.grade, 0) + 1

    complex_ids = sorted({c.complex_id for c in conclusions})

    precision = compute_precision_at_1(conclusions, labels)
    single_cov = compute_single_confirm_coverage(conclusions)
    multi_rate = compute_multi_prob_rate(conclusions)
    demand_solved = compute_demand_weighted_solved(conclusions, demand)

    # labeled_count = 라벨이 있는 결론 수
    label_keys = {(lbl.get("complex_id", ""), lbl.get("dong", "")) for lbl in labels}
    labeled_count = sum(
        1 for c in conclusions if (c.complex_id, c.dong) in label_keys
    )

    return {
        "total_conclusions": len(conclusions),
        "complex_ids": complex_ids,
        "grade_counts": grade_counts,
        "precision_at_1": round(precision, 4),
        "single_confirm_coverage": round(single_cov, 4),
        "multi_prob_rate": round(multi_rate, 4),
        "demand_weighted_solved": round(demand_solved, 4),
        "labeled_count": labeled_count,
    }
