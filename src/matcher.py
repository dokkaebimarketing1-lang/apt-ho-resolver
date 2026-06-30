"""Supabase match_units RPC + Supabase DB 매칭 (Todo 21).

match_units RPC(SQL) + Python matcher 클라이언트.
정확 전용면적(cm²) + 타입(A/B/C) 매칭 (A82).
"""

from __future__ import annotations

from typing import Any


def match_ho(
    listings: list[dict[str, Any]],
    unit_master: list[dict[str, Any]],
    *,
    complex_id: str,
    dong: str | None = None,
    area_cm2: int | None = None,
    area_type: str | None = None,
    direction: str | None = None,
    floor_min: int | None = None,
    floor_max: int | None = None,
    price_manwon: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """DB 매칭 없이 Python에서 직접 후보 필터링 (mock/fallback).

    Args:
        listings: 매물 리스트. 각 dict: {complex_id, dong, area2(㎡), direction, floor, ...}
        unit_master: unit_master 행 리스트. 각 dict: {canonical_ho_id, dong, ho,
            floor, area_exclusive(cm²), area_type, direction, ...}
        complex_id: 단지 ID.
        dong: 동 번호 (선택).
        area_cm2: 정확 전용면적(cm²) (선택).
        area_type: 평형구분명 (예: "84A") (선택).
        direction: 향 (선택).
        floor_min: 최소 층 (선택).
        floor_max: 최대 층 (선택).
        price_manwon: 거래가격(만원) (선택, 가격 근접도 정렬용).
        limit: 후보 최대 개수.

    Returns:
        후보 호 리스트 [{canonical_ho_id, ho, dong, floor, area_exclusive,
        area_type, direction, score}, ...] score 높은 순 정렬.
    """
    candidates: list[dict[str, Any]] = []

    for unit in unit_master:
        # 필수: 같은 단지
        if unit.get("complex_id") != complex_id:
            continue

        # 동 필터
        if dong is not None and unit.get("dong") != dong:
            continue

        # 면적 필터 (±500cm² tolerance)
        if area_cm2 is not None:
            unit_area = unit.get("area_exclusive")
            if unit_area is None:
                continue
            if abs(int(unit_area) - area_cm2) > 500:
                continue

        # 평형구분명 필터
        if area_type is not None and unit.get("area_type") != area_type:
            continue

        # 향 필터
        if direction is not None and unit.get("direction") != direction:
            continue

        # 층 범위 필터
        unit_floor = unit.get("floor")
        if unit_floor is not None:
            if floor_min is not None and int(unit_floor) < floor_min:
                continue
            if floor_max is not None and int(unit_floor) > floor_max:
                continue

        # 점수 계산 (높을수록 좋음)
        score = 0.0

        # 향 일치 (가중치 높음)
        if direction is not None and unit.get("direction") == direction:
            score += 10.0

        # 층 근접도
        if unit_floor is not None and floor_min is not None:
            dist = abs(int(unit_floor) - floor_min)
            score += max(0, 5.0 - dist * 0.5)

        # 가격 근접도 (간접 — 면적이 비슷한 호가 가격도 비슷)
        if price_manwon is not None:
            unit_price = unit.get("public_price")
            if unit_price is not None:
                ratio = min(price_manwon, int(unit_price)) / max(
                    price_manwon, int(unit_price)
                )
                if ratio > 0.7:
                    score += ratio * 3.0

        candidates.append({
            "canonical_ho_id": unit.get("canonical_ho_id"),
            "ho": unit.get("ho"),
            "dong": unit.get("dong"),
            "floor": unit_floor,
            "area_exclusive": unit.get("area_exclusive"),
            "area_type": unit.get("area_type"),
            "direction": unit.get("direction"),
            "score": score,
        })

    # 점수 높은 순 정렬
    candidates.sort(key=lambda c: c["score"], reverse=True)

    if limit > 0:
        candidates = candidates[:limit]

    # 다호 후보 시 확률 리스트로 변환 (A81)
    if candidates:
        total_score = sum(c["score"] for c in candidates)
        if total_score > 0:
            for c in candidates:
                c["probability"] = round(c["score"] / total_score, 4)
        else:
            equal_prob = round(1.0 / len(candidates), 4)
            for c in candidates:
                c["probability"] = equal_prob

    return candidates


__all__ = ["match_ho"]
