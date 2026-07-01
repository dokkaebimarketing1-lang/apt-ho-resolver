"""전유부 역추론 배치도 - 호 끝 2자리=라인, 면적 클러스터링으로 타입/향 추론.

설계 원칙 (A83 - 제일 큰 레버):
- 배치도 실물 없이 전유부 데이터만으로 라인/타입/향 추론
- 호 끝 2자리 = 라인 번호 (일반적 한국 아파트 호 체계)
- 같은 라인 = 같은 타입 + 같은 향 (건축 구조적 제약)
- 모든 결과는 is_estimate=True (역추론 결과는 추정)
- 호 끝 2자리가 라인이 아닌 순차 번호 단지는 스킵 (None 반환)

관련 결정: A83 (역추론 배치도), A82 (정확 전용면적/타입), A4 (Solved 단지 이분법)
의존: Todo 3 (domain.py Pillar.UNIT_RESOLUTION), Todo 31 (ho_key.py 정규화 패턴)
입력: 전유부 단위 리스트 [{ho, area_exclusive, floor, dong}, ...]
"""

from __future__ import annotations

import re
import statistics
from typing import Any

__all__ = [
    "extract_line_from_ho",
    "cluster_areas_by_line",
    "infer_line_type",
    "infer_line_direction",
    "infer_floorplan",
]

# 면적 클러스터링 갭 - 이 갭보다 큰 면적 차이는 다른 타입 (m^2 단위)
_AREA_CLUSTER_GAP_M2 = 5.0

# 호 최소 자릿수 (3자리 미만 = 라인 추출 불가)
_HO_MIN_DIGITS = 3


def extract_line_from_ho(ho: str) -> str | None:
    """호 끝 2자리를 라인 번호로 추출.

    정규화 규칙:
    1. 숫자만 추출
    2. 앞채우기 4자리 (``"503"`` -> ``"0503"``)
    3. 끝 2자리 반환 (``"0503"`` -> ``"03"``)

    Args:
        ho: 호 표기 문자열 (``"1503"``, ``"503"``, ``"1503호"`` 등).

    Returns:
        2자리 라인 번호 문자열 (``"03"``, ``"04"`` 등).
        호가 3자리 미만이거나 숫자가 없으면 ``None``.
    """
    digits = re.sub(r"[^0-9]", "", ho.strip())
    if len(digits) < _HO_MIN_DIGITS:
        return None
    normalized = digits.zfill(4)
    return normalized[-2:]


def cluster_areas_by_line(
    units: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """라인별 전용면적 그룹화.

    각 단위의 호에서 라인을 추출하고, 라인별로 전용면적을 그룹화한다.

    Args:
        units: 전유부 단위 리스트. 각 dict은 ``ho`` 와 ``area_exclusive`` 키를 포함.

    Returns:
        ``{라인: [면적, ...]}`` 딕셔너리.
        라인 추출 실패 또는 면적 누락 단위는 제외.
    """
    result: dict[str, list[float]] = {}
    for unit in units:
        line = extract_line_from_ho(str(unit.get("ho", "")))
        if line is None:
            continue
        area = unit.get("area_exclusive")
        if area is None:
            continue
        result.setdefault(line, []).append(float(area))
    return result


def infer_line_type(units: list[dict[str, Any]]) -> dict[str, str]:
    """면적 패턴으로 라인별 타입(A/B/C) 클러스터링.

    알고리즘:
    1. 라인별 중앙면적 계산
    2. 중앙면적을 오름차순 정렬
    3. 갭 기반 클러스터링 (갭 > ``_AREA_CLUSTER_GAP_M2`` -> 다른 타입)
    4. 클러스터에 A, B, C, ... 라벨 할당 (면적 작은 순)

    Args:
        units: 전유부 단위 리스트.

    Returns:
        ``{라인: 타입문자}`` 딕셔너리 (예: ``{"01": "A", "02": "B"}``).
        입력이 빈 경우 빈 딕셔너리.
    """
    areas_by_line = cluster_areas_by_line(units)
    if not areas_by_line:
        return {}

    # 라인별 중앙면적, 오름차순 정렬
    line_medians: list[tuple[str, float]] = sorted(
        (
            (line, statistics.median(areas))
            for line, areas in areas_by_line.items()
        ),
        key=lambda x: x[1],
    )

    # 갭 기반 클러스터링 — A-Z 넘어가면 숫자로 표기
    type_labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + [str(i) for i in range(100)]
    result: dict[str, str] = {}
    cluster_idx = 0
    prev_area: float | None = None

    for line, median in line_medians:
        if prev_area is not None and median - prev_area > _AREA_CLUSTER_GAP_M2:
            cluster_idx += 1
        result[line] = type_labels[cluster_idx]
        prev_area = median

    return result


def infer_line_direction(
    line_facts: dict[str, str],
    building_shape: str | None = None,
) -> dict[str, str]:
    """(라인, 향) 매핑 추론 — 라인 수에 따라 2·3·4향 자동 대응.

    한국 아파트 관행:
    - 판상형(짝수 라인, 계단식): 전반부=S, 후반부=N (예: 01/02=S, 03/04=N)
    - Y자형(3라인): 01=S(정남), 02=SE(남동), 03=SW(남서) — 번호순 시계방향
    - T자형(3라인): 01=S(정남), 02=E(동), 03=W(서)
    - 口자형(4라인 이상): 01=S, 02=E, 03=W, 04=N — 시계방향

    Args:
        line_facts: ``{라인: 타입}`` 딕셔너리.
        building_shape: 건물 형태 힌트 (``"flat"``/``"tower"``/``"y"``/``"t"``).
            None이면 라인 수로 자동 판단.

    Returns:
        ``{라인: 향코드}`` 딕셔너리.
    """
    if not line_facts:
        return {}

    sorted_lines = sorted(line_facts.keys(), key=int)
    n = len(sorted_lines)

    if n <= 2:
        # 1~2라인: 단순 S/N
        return {
            line: "S" if idx < (n + 1) // 2 else "N"
            for idx, line in enumerate(sorted_lines)
        }

    elif n == 3:
        # 3라인: Y자형(S/SE/SW) 또는 T자형(S/E/W)
        if building_shape in ("t", "tower"):
            directions = ["S", "E", "W"]
        else:
            directions = ["S", "SE", "SW"]  # default Y자형
        return dict(zip(sorted_lines, directions))

    elif n == 4:
        # 4라인: 판상형(S/S/N/N) or 口자형(S/E/W/N)
        if building_shape in ("square", "tower"):
            directions = ["S", "E", "W", "N"]
        else:
            mid = n // 2
            directions = ["S"] * mid + ["N"] * (n - mid)
        return dict(zip(sorted_lines, directions))

    elif n == 5:
        # 5라인: 전반부 S, 후반부 N, 중간 라인은 SE
        mid = n // 2
        directions = ["S"] * mid + ["SE"] + ["N"] * (n - mid - 1)
        return dict(zip(sorted_lines, directions))

    else:
        # 6라인 이상: 균등 분할 S/N
        mid = n // 2
        directions = ["S"] * mid + ["N"] * (n - mid)
        return dict(zip(sorted_lines, directions))


def _is_sequential_numbering(units: list[dict[str, Any]]) -> bool:
    """순차 번호 체계 감지 - 호 끝 2자리가 라인이 아닌 경우.

    순차 번호 체계: 각 층마다 호 번호가 이어지는 방식
    (예: 1층 01-04, 2층 05-08, 3층 09-12).
    이 경우 끝 2자리가 라인이 아니라 순차 번호이므로 역추론 불가.

    감지 조건: 2개 이상 층의 데이터가 있고,
    모든 "라인"(끝 2자리)이 1개 층에만 존재.

    Args:
        units: 전유부 단위 리스트.

    Returns:
        순차 번호 체계면 ``True``, 라인 체계면 ``False``.
    """
    lines_floors: dict[str, set[int]] = {}
    for unit in units:
        line = extract_line_from_ho(str(unit.get("ho", "")))
        if line is None:
            continue
        floor = unit.get("floor")
        if floor is None:
            continue
        lines_floors.setdefault(line, set()).add(int(floor))

    if not lines_floors:
        return False

    all_floors = {f for fs in lines_floors.values() for f in fs}
    if len(all_floors) <= 1:
        # 1개 층만 있으면 판단 불가 -> 라인 체계로 간주
        return False

    # 모든 라인이 1개 층에만 존재 = 순차 번호
    return all(len(floors) <= 1 for floors in lines_floors.values())


def infer_floorplan(
    units: list[dict[str, Any]],
    building_shape: str | None = None,
) -> list[dict[str, Any]] | None:
    """전체 역추론 파이프라인.

    입력: ``[{ho, area_exclusive, floor, dong}, ...]``
    출력: ``[{dong, line, area_type, direction, is_estimate}, ...]``

    파이프라인:
    1. 동별 그룹화
    2. 순차 번호 체계 감지 → 해당 시 ``None`` 반환
    3. 라인별 타입 추론 (면적 클러스터링)
    4. 라인별 향 추론 (2·3·4향 자동 대응, building_shape 힌트)
    5. 결과 조립 (동x라인 조합당 1개 엔트리, ``is_estimate=True``)

    Args:
        units: 전유부 단위 리스트.
        building_shape: 건물 형태 힌트 (``"flat"``/``"y"``/``"t"``/``"tower"``/``"square"``).
            None이면 라인 수로 자동 판단.

    Returns:
        역추론 결과 리스트. 순차 번호 체계 단지거나 빈 입력이면 ``None``.
    """
    if not units:
        return None

    # 동별 그룹화
    units_by_dong: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        dong = str(unit.get("dong", ""))
        units_by_dong.setdefault(dong, []).append(unit)

    all_results: list[dict[str, Any]] = []
    for dong, dong_units in units_by_dong.items():
        # 순차 번호 체계 감지 - 하나의 동이라도 순차면 전체 스킵
        if _is_sequential_numbering(dong_units):
            return None

        # 타입 추론
        line_types = infer_line_type(dong_units)
        if not line_types:
            continue

        # 향 추론 (건물형태 전달)
        line_directions = infer_line_direction(line_types, building_shape)

        # 결과 조립 - (dong, line) 조합당 1개 엔트리
        seen: set[str] = set()
        for unit in dong_units:
            line = extract_line_from_ho(str(unit.get("ho", "")))
            if line is None or line in seen:
                continue
            seen.add(line)
            all_results.append({
                "dong": dong,
                "line": line,
                "area_type": line_types.get(line, ""),
                "direction": line_directions.get(line, ""),
                "is_estimate": True,
            })

    return all_results if all_results else None
