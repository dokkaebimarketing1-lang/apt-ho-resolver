"""추론 인터페이스 — 단지 추론(infer_complex) + 세대 질의(infer_unit).

Fellegi-Sunter 기반 매칭 엔진을 통해 매물(또는 사용자 질의)을
unit_master 정답표와 매칭하여 호를 추정한다.

설계 원칙:
- infer_complex: 단지명 + 매물 리스트 → F-S 매칭 → HoConclusion 리스트
- infer_unit: 단일 세대 질의(동+층+향+면적) → 후보 호 → HoConclusion
- 다호 후보 시 [{ho, probability}] 확률 리스트 출력 (A81)
- is_estimate=True 기본
"""

from __future__ import annotations

import math
from typing import Any

from src.domain import HoConclusion

__all__ = [
    "infer_complex",
    "infer_unit",
]

# ---------------------------------------------------------------------------
# Constants: 기본 m/u 확률 (라벨 학습 전 초기값)
# ---------------------------------------------------------------------------

_DEFAULT_M_PROBS: dict[str, float] = {
    "dong": 0.95,
    "floor": 0.80,
    "area_type": 0.85,
    "direction": 0.70,
}

_DEFAULT_U_PROBS: dict[str, float] = {
    "dong": 0.05,
    "floor": 0.25,
    "area_type": 0.15,
    "direction": 0.35,
}

_AREA_TOLERANCE_M2: float = 5.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """dict 또는 object에서 안전하게 값 추출."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _compare_str(val1: Any, val2: Any) -> int:
    """두 값을 문자열 비교. 1=일치, 0=불일치, -1=비교불가."""
    if val1 is None or val2 is None:
        return -1
    s1 = str(val1).strip().upper()
    s2 = str(val2).strip().upper()
    if not s1 or not s2:
        return -1
    return 1 if s1 == s2 else 0


def _extract_floor(raw: Any) -> int | None:
    """Listing.floor_info 또는 숫자에서 층 번호 추출."""
    if raw is None:
        return None
    try:
        s = str(raw)
        if "/" in s:
            s = s.split("/")[-1].strip()
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _fellegi_sunter_weight(
    listing: dict[str, Any] | Any,
    unit: dict[str, Any],
    m_probs: dict[str, float],
    u_probs: dict[str, float],
) -> float:
    """listing과 unit 사이의 FS 매치 가중치 계산.

    각 필드(dong, floor, area_type, direction)에 대해:
      일치 시: log(m/u)
      불일치 시: log((1-m)/(1-u))
    """
    total = 0.0

    # --- dong 비교 ---
    lv = _get(listing, "dong")
    uv = _get(unit, "dong")
    cmp = _compare_str(lv, uv)
    if cmp != -1:
        m = m_probs.get("dong", _DEFAULT_M_PROBS["dong"])
        u = u_probs.get("dong", _DEFAULT_U_PROBS["dong"])
        if cmp == 1 and m > 0 and u > 0:
            total += math.log(m / u)
        elif cmp == 0 and m < 1 and u < 1:
            total += math.log((1 - m) / (1 - u))

    # --- area_type 비교 ---
    lv = _get(listing, "area_type")
    uv = _get(unit, "area_type")
    cmp = _compare_str(lv, uv)
    if cmp != -1:
        m = m_probs.get("area_type", _DEFAULT_M_PROBS["area_type"])
        u = u_probs.get("area_type", _DEFAULT_U_PROBS["area_type"])
        if cmp == 1 and m > 0 and u > 0:
            total += math.log(m / u)
        elif cmp == 0 and m < 1 and u < 1:
            total += math.log((1 - m) / (1 - u))

    # --- direction 비교 ---
    lv = _get(listing, "direction")
    uv = _get(unit, "direction")
    cmp = _compare_str(lv, uv)
    if cmp != -1:
        m = m_probs.get("direction", _DEFAULT_M_PROBS["direction"])
        u = u_probs.get("direction", _DEFAULT_U_PROBS["direction"])
        if cmp == 1 and m > 0 and u > 0:
            total += math.log(m / u)
        elif cmp == 0 and m < 1 and u < 1:
            total += math.log((1 - m) / (1 - u))

    # --- floor 비교 (±1층 허용) ---
    l_floor = _extract_floor(_get(listing, "floor") or _get(listing, "floor_info"))
    u_floor = _extract_floor(_get(unit, "floor"))
    if l_floor is not None and u_floor is not None:
        floor_match = abs(l_floor - u_floor) <= 1
        m = m_probs.get("floor", _DEFAULT_M_PROBS["floor"])
        u = u_probs.get("floor", _DEFAULT_U_PROBS["floor"])
        if floor_match and m > 0 and u > 0:
            total += math.log(m / u)
        elif not floor_match and m < 1 and u < 1:
            total += math.log((1 - m) / (1 - u))

    return total


def _block_candidates(
    listing: dict[str, Any] | Any,
    unit_master: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """단지+동+면적으로 후보 차단.

    blocking 조건:
    1. complex_id 일치
    2. 동 일치 (listing에 동 정보 있을 경우)
    3. 면적 차이가 _AREA_TOLERANCE_M2 이내
    """
    if not unit_master:
        return []

    listing_cid = str(_get(listing, "complex_id", ""))
    listing_dong = str(_get(listing, "dong", ""))
    listing_area = _get(listing, "area2") or _get(listing, "area_exclusive")

    try:
        listing_area_f = float(listing_area) if listing_area else None
    except (ValueError, TypeError):
        listing_area_f = None

    candidates: list[dict[str, Any]] = []
    for unit in unit_master:
        # 1. complex_id
        unit_cid = str(_get(unit, "complex_id", ""))
        if listing_cid and unit_cid and unit_cid != listing_cid:
            continue

        # 2. 동 (둘 다 있을 때만)
        unit_dong = str(_get(unit, "dong", ""))
        if listing_dong and unit_dong and listing_dong != unit_dong:
            continue

        # 3. 면적
        unit_area = _get(unit, "area2") or _get(unit, "area_exclusive")
        if listing_area_f is not None and unit_area is not None:
            try:
                if abs(listing_area_f - float(unit_area)) > _AREA_TOLERANCE_M2:
                    continue
            except (ValueError, TypeError):
                continue

        candidates.append(unit)

    return candidates


def _weight_to_probability(
    weight: float,
    max_weight: float | None = None,
) -> float:
    """FS 가중치 → 확률 변환 (sigmoid 기반)."""
    if max_weight is not None and max_weight > 0 and max_weight != weight:
        normalized = weight / max_weight
    elif weight > 0:
        normalized = min(weight / 5.0, 5.0)  # soft cap
    else:
        normalized = max(weight / 5.0, -5.0)  # soft cap
    return 1.0 / (1.0 + math.exp(-normalized))


def _filter_unit_master(
    unit_master: list[dict[str, Any]],
    complex_id: str,
    dong: str,
    floor: int | None = None,
    area_type: str | None = None,
    direction: str | None = None,
) -> list[dict[str, Any]]:
    """unit_master를 질의 조건으로 필터링."""
    results: list[dict[str, Any]] = []
    for unit in unit_master:
        if str(_get(unit, "complex_id", "")) != complex_id:
            continue
        if str(_get(unit, "dong", "")) != dong:
            continue
        if area_type and str(_get(unit, "area_type", "")) != area_type:
            continue
        if direction and _compare_str(_get(unit, "direction"), direction) != 1:
            continue
        results.append(unit)
    return results


# ---------------------------------------------------------------------------
# Main inference functions
# ---------------------------------------------------------------------------


def infer_complex(
    complex_name: str,
    listings: list[dict[str, Any]],
    unit_master: list[dict[str, Any]],
    m_probs: dict[str, float] | None = None,
    u_probs: dict[str, float] | None = None,
) -> list[HoConclusion]:
    """단지명 → 전 매물 호 리스트. F-S 매칭 + 다호확률리스트.

    Args:
        complex_name: 단지명 (unit_master 필터링용).
        listings: 매물 리스트 (dict 또는 Listing 객체).
        unit_master: 해당 단지의 정답표 리스트.
        m_probs: 필드별 m-확률. None=기본값.
        u_probs: 필드별 u-확률. None=기본값.

    Returns:
        각 매물별 HoConclusion 리스트.
    """
    m_probs = m_probs or dict(_DEFAULT_M_PROBS)
    u_probs = u_probs or dict(_DEFAULT_U_PROBS)

    # unit_master를 단지명으로 필터링 (complex_name 기준)
    complex_units = [
        u for u in unit_master
        if complex_name in (str(_get(u, "complex_name", "")), "")
        or str(_get(u, "complex_id", "")) == complex_name
    ]

    conclusions: list[HoConclusion] = []
    for listing in listings:
        candidates = _block_candidates(listing, complex_units)
        if not candidates:
            conclusions.append(HoConclusion(
                complex_id=_get(listing, "complex_id", ""),
                dong=_get(listing, "dong", ""),
                candidate_hos=[],
                ho_final=None,
                is_estimate=True,
            ))
            continue

        # FS 가중치 계산
        scored: list[tuple[float, dict[str, Any]]] = []
        for unit in candidates:
            weight = _fellegi_sunter_weight(listing, unit, m_probs, u_probs)
            scored.append((weight, unit))
        scored.sort(key=lambda x: x[0], reverse=True)

        max_w = scored[0][0] if scored else 0.0
        candidate_hos: list[dict[str, Any]] = []
        seen_hos: set[str] = set()
        for weight, unit in scored:
            ho = str(_get(unit, "ho", ""))
            if not ho or ho in seen_hos:
                continue
            seen_hos.add(ho)
            prob = _weight_to_probability(weight, max_w)
            candidate_hos.append({"ho": ho, "probability": round(prob, 4)})

        # 확률 정규화
        if len(candidate_hos) > 1:
            total_prob = sum(c["probability"] for c in candidate_hos)
            if total_prob > 0:
                for c in candidate_hos:
                    c["probability"] = round(c["probability"] / total_prob, 4)

        # 1순위 호 = ho_final
        best_ho = candidate_hos[0]["ho"] if candidate_hos else None
        conclusions.append(HoConclusion(
            complex_id=_get(listing, "complex_id", ""),
            dong=_get(listing, "dong", ""),
            candidate_hos=candidate_hos,
            ho_final=best_ho,
            is_estimate=True,
        ))

    return conclusions


def infer_unit(
    complex_id: str,
    dong: str,
    floor: int,
    area_type: str,
    direction: str,
    unit_master: list[dict[str, Any]],
    m_probs: dict[str, float] | None = None,
    u_probs: dict[str, float] | None = None,
) -> HoConclusion:
    """세대 질의. 단지+동+층±향/면적 → 호 후보/확정.

    Args:
        complex_id: 단지 식별자.
        dong: 동 (예: "101").
        floor: 층 번호.
        area_type: 면적 타입 (예: "84A", "59B").
        direction: 향 (영문 코드 "S", "SE" 등).
        unit_master: 정답표 리스트.
        m_probs: 필드별 m-확률. None=기본값.
        u_probs: 필드별 u-확률. None=기본값.

    Returns:
        HoConclusion — 후보 호 리스트(candidate_hos) + 최종 호(ho_final).
        증거 부족 시 ho_final=None.
    """
    m_probs = m_probs or dict(_DEFAULT_M_PROBS)
    u_probs = u_probs or dict(_DEFAULT_U_PROBS)

    # 1. complex_id + dong으로 필터링
    candidates = _filter_unit_master(
        unit_master, complex_id, dong, area_type=area_type, direction=direction,
    )

    # 2. 층 근접도로 스코어링
    scored: list[tuple[float, dict[str, Any]]] = []
    for unit in candidates:
        u_floor = _extract_floor(_get(unit, "floor"))
        if u_floor is not None:
            floor_dist = abs(floor - u_floor)
            # 층이 가까울수록 높은 점수
            floor_score = math.exp(-0.2 * floor_dist)
        else:
            floor_score = 0.5  # 층 정보 없으면 중립

        # F-S: direction/area_type 비교
        mock_listing = {
            "complex_id": complex_id,
            "dong": dong,
            "area_type": area_type,
            "direction": direction,
        }
        fs_weight = _fellegi_sunter_weight(mock_listing, unit, m_probs, u_probs)
        combined = fs_weight + math.log(floor_score) if floor_score > 0 else fs_weight
        scored.append((combined, unit))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return HoConclusion(
            complex_id=complex_id,
            dong=dong,
            candidate_hos=[],
            ho_final=None,
            is_estimate=True,
        )

    # 3. 후보 호 리스트 조립
    max_w = scored[0][0] if scored else 0.0
    candidate_hos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for weight, unit in scored:
        ho = str(_get(unit, "ho", ""))
        if not ho or ho in seen:
            continue
        seen.add(ho)
        prob = _weight_to_probability(weight, max_w)
        candidate_hos.append({"ho": ho, "probability": round(prob, 4)})

    if len(candidate_hos) > 1:
        total_prob = sum(c["probability"] for c in candidate_hos)
        if total_prob > 0:
            for c in candidate_hos:
                c["probability"] = round(c["probability"] / total_prob, 4)

    best_ho = candidate_hos[0]["ho"] if candidate_hos else None
    return HoConclusion(
        complex_id=complex_id,
        dong=dong,
        candidate_hos=candidate_hos,
        ho_final=best_ho,
        is_estimate=True,
    )
