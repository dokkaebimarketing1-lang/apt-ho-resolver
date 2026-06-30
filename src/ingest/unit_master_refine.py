"""unit_master 정제 + 4개 소스 충돌 해결 + 최종 정답지 확정 (Todo 34).

4개 소스(공시가격, 집합건물호, 건축인허가, 대장 전유부)에서 적재된
unit_master 데이터를 canonical_ho_id 기준으로 정제.

충돌 우선순위 (A21):
    registry > public_price > building_registry > housing_permit
"""

from __future__ import annotations

from typing import Any

# 출처 우선순위 (높을수록 우선)
SOURCE_PRIORITY: dict[str, int] = {
    "registry": 4,           # 등기부 — 최우선
    "public_price": 3,       # 공시가격 (등기부 기반)
    "building_registry": 2,  # 건축물대장 전유부
    "housing_permit": 1,     # 건축인허가
}


def _resolve_field(
    field: str,
    rows: list[dict[str, Any]],
) -> Any:
    """같은 canonical_ho_id를 가진 여러 행 중 충돌 필드 해결.

    우선순위가 가장 높은 소스의 값을 채택한다.
    모든 값이 같으면 바로 반환.
    """
    # 소스별 값 수집
    values: dict[str, set[Any]] = {}
    for row in rows:
        source = row.get("source", "unknown")
        val = row.get(field)
        if val is not None:
            values.setdefault(source, set()).add(val)

    # 모든 소스에서 동일한 값이면 충돌 없음 → 첫 번째 값 반환
    all_vals = set()
    for vset in values.values():
        all_vals.update(vset)
    if len(all_vals) <= 1:
        return next(iter(all_vals)) if all_vals else None

    # 우선순위순으로 정렬된 소스 목록
    sorted_sources = sorted(
        values.keys(),
        key=lambda s: SOURCE_PRIORITY.get(s, 0),
        reverse=True,
    )

    # 최우선 소스의 값 사용
    best_source = sorted_sources[0]
    best_val = next(iter(values[best_source]))
    return best_val


def resolve_conflicts(
    rows: list[dict[str, Any]],
    *,
    fields: tuple[str, ...] = (
        "dong", "floor", "area_exclusive", "area_type", "direction",
    ),
) -> dict[str, Any]:
    """4개 소스 간 충돌 해결 → 정제된 단일 행 반환.

    모든 canonical_ho_id가 같은 여러 행을 하나로 병합한다.
    각 필드는 우선순위에 따라 해결한다.

    Args:
        rows: 같은 canonical_ho_id를 가진 unit_master 행 리스트.
            각 행은 {field: value, "source": str, "canonical_ho_id": str, ...}
        fields: 충돌 해결할 필드 목록.

    Returns:
        정제된 단일 행 dict. 충돌 정보는 "_conflicts" 키에 저장.
    """
    if not rows:
        return {}

    conflicts: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "canonical_ho_id": rows[0].get("canonical_ho_id"),
        "complex_id": rows[0].get("complex_id"),
        "ho": rows[0].get("ho"),
    }

    for field in fields:
        result[field] = _resolve_field(field, rows)

        # 충돌 감지
        field_values: set[Any] = set()
        for row in rows:
            val = row.get(field)
            if val is not None:
                field_values.add(val)

        if len(field_values) > 1:
            conflicts.append({
                "field": field,
                "values": list(field_values),
                "resolved_to": result[field],
            })

    result["_conflicts"] = conflicts
    result["_conflict_count"] = len(conflicts)

    # 소스 통합
    sources: set[str] = set()
    for row in rows:
        src = row.get("source", "")
        if src:
            sources.add(src)
    result["source"] = sorted(sources)

    return result


def deduplicate(
    rows: list[dict[str, Any]],
    *,
    key: str = "canonical_ho_id",
) -> list[list[dict[str, Any]]]:
    """canonical_ho_id 기준으로 행들을 중복 그룹으로 분류.

    Args:
        rows: unit_master 행 리스트.
        key: 그룹화 키 필드명 (기본값: canonical_ho_id).

    Returns:
        그룹 리스트. 각 그룹은 같은 키를 가진 행들의 리스트.
        키당 1개 행만 있으면 그룹 크기는 1.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        k = row.get(key, "")
        if k:
            groups.setdefault(k, []).append(row)
    return list(groups.values())


def refine_unit_master(
    rows: list[dict[str, Any]],
    *,
    conflict_threshold: float = 0.05,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """unit_master 전체 정제 파이프라인.

    1. canonical_ho_id 기준 중복 제거 (중복 그룹 식별)
    2. 충돌 해결 (우선순위)
    3. 최종 unit_master_clean 생성

    Args:
        rows: unit_master 행 리스트.
        conflict_threshold: 충돌율 임계값 (이 값 초과 시 warning).

    Returns:
        (clean_rows, report) 튜플.
        clean_rows: 정제된 행 리스트 (중복 0).
        report: {total, clean_count, conflict_count, conflict_rate, ...}
    """
    total = len(rows)
    groups = deduplicate(rows)
    clean_rows: list[dict[str, Any]] = []
    conflict_count = 0
    unresolved = 0

    for group in groups:
        if len(group) == 1:
            row = dict(group[0])
            row["_conflicts"] = []
            row["_conflict_count"] = 0
            clean_rows.append(row)
        else:
            resolved = resolve_conflicts(group)
            if resolved["_conflict_count"] > 0:
                conflict_count += 1
            # 해결 불가 충돌 (여전히 여러 값이 충돌 해결 안 됨)
            unresolved_fields = [
                c for c in resolved["_conflicts"]
                if len(c["values"]) > 1
            ]
            if unresolved_fields:
                unresolved += 1
            clean_rows.append(resolved)

    conflict_rate = conflict_count / total if total > 0 else 0.0

    report = {
        "total": total,
        "clean_count": len(clean_rows),
        "conflict_count": conflict_count,
        "unresolved_count": unresolved,
        "conflict_rate": round(conflict_rate, 4),
        "warning": conflict_rate > conflict_threshold,
    }

    return clean_rows, report


__all__ = [
    "SOURCE_PRIORITY",
    "_resolve_field",
    "resolve_conflicts",
    "deduplicate",
    "refine_unit_master",
]
