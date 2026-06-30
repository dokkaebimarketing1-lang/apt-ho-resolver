"""호 키 정합 모듈 — 4개 소스 호 표기 정규화 → canonical ho_id.

설계 원칙:
- 4개 소스(공시가격 호 / 등기 호 / 대장 호명칭 / 분양 호수) 교차 검증
- 정답 신뢰도 우선순위 (A21): 등기 > 공시 > 대장 > 분양
- 동 정합 생략 금지 — 동이 안 맞으면 호 정합도 틀림
- 정합 불가 = None 반환 (DB 없으므로 evidence_log 대체)
"""

from __future__ import annotations

import re

__all__ = [
    "normalize_ho",
    "normalize_dong",
    "resolve_canonical",
    "SOURCE_PRIORITY",
]

# 정답 신뢰도 우선순위 (A21): 등기 > 공시 > 대장 > 분양
SOURCE_PRIORITY: tuple[str, ...] = (
    "registry",           # 집합건물 등기 — 최우선
    "public_price",       # 공시가격
    "building_registry",  # 건축물대장 전유부
    "sale",               # 분양
)


def normalize_ho(raw: str, source: str) -> str:
    """4개 소스의 호 표기를 canonical ho_id로 정규화.

    정규화 규칙:
    1. 접미사 ``호`` 제거
    2. ``동`` 접두사 제거
    3. 복합 표기 ``15-0301`` → 층(15) + 라인(03) 결합 → ``1503``
    4. 숫자만 추출 (한글/공백/특수문자 제거)
    5. 앞채우기 4자리 (``503`` → ``0503``)

    Args:
        raw: 원시 호 표기 문자열.
        source: 소스 식별자
            (``public_price`` / ``registry`` / ``building_registry`` / ``sale``).

    Returns:
        4자리 canonical ho_id 문자열 (예: ``"1503"``).

    Raises:
        ValueError: 빈 문자열이거나 정규화 후 빈 결과.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError(f"빈 호 표기: source={source!r}")

    if source == "building_registry" and "-" in raw:
        # 복합 표기 "15-0301" → 층(15) + 라인(03) → "1503"
        parts = raw.split("-", 1)
        floor_part = parts[0].strip()
        unit_part = parts[1].strip()
        floor_digits = re.sub(r"[^0-9]", "", floor_part)
        unit_digits = re.sub(r"[^0-9]", "", unit_part)
        if not floor_digits or not unit_digits:
            raise ValueError(
                f"복합 표기 정규화 실패: raw={raw!r}, "
                f"source={source!r}"
            )
        # unit_digits 앞 2자리 = 라인 번호
        line = unit_digits[:2]
        result = floor_digits + line
    else:
        # 일반 정규화: 숫자만 추출
        result = re.sub(r"[^0-9]", "", raw)

    if not result:
        raise ValueError(
            f"정규화 후 빈 결과: raw={raw!r}, source={source!r}"
        )

    # 앞채우기 4자리
    return result.zfill(4)


def normalize_dong(raw: str, source: str) -> str:
    """동명 정규화.

    ``"101동"`` → ``"101"``, ``"101"`` → ``"101"``.
    동 접미사/접두사를 제거하고 숫자 동 번호를 반환한다.

    Args:
        raw: 원시 동 표기 (``"101동"``, ``"101"`` 등).
        source: 소스 식별자 (통일 인터페이스용, 로직에 영향 없음).

    Returns:
        숫자 동 번호 문자열 (예: ``"101"``).

    Raises:
        ValueError: 빈 문자열이거나 정규화 후 빈 결과.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError(f"빈 동 표기: source={source!r}")

    # 숫자만 추출 ("동" 접미사/접두사/특수문자 제거)
    result = re.sub(r"[^0-9]", "", raw)

    if not result:
        raise ValueError(
            f"동 정규화 후 빈 결과: raw={raw!r}, source={source!r}"
        )

    return result


def resolve_canonical(
    ho_variants: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    """4개 소스의 (동, 호)를 받아 canonical (dong, ho_id) 확정.

    정답 신뢰도 우선순위 (A21):
    ``registry > public_price > building_registry > sale``
    동이 다른 경우 우선순위 최고 소스의 동을 사용한다.
    호가 다른 경우도 동일하게 우선순위로 결정한다.

    Args:
        ho_variants: ``{source: (dong_raw, ho_raw)}`` 딕셔너리.
            최소 1개 이상의 소스가 있어야 한다.

    Returns:
        ``(canonical_dong, canonical_ho_id)`` 튜플.
        정합 불가 (모든 소스 정규화 실패 또는 빈 입력) 시 ``None``.
    """
    if not ho_variants:
        return None

    normalized: dict[str, tuple[str, str]] = {}
    for source, (dong_raw, ho_raw) in ho_variants.items():
        try:
            norm_dong = normalize_dong(dong_raw, source)
            norm_ho = normalize_ho(ho_raw, source)
            normalized[source] = (norm_dong, norm_ho)
        except ValueError:
            # 정규화 실패 소스는 건너뜀 (evidence_log 기록이지만
            # DB 없으므로 생략)
            continue

    if not normalized:
        return None

    # 우선순위순으로 가용 소스 정렬
    available: list[str] = [
        s for s in SOURCE_PRIORITY if s in normalized
    ]

    if not available:
        # 우선순위 목록에 없는 소스만 있는 경우 첫 번째 사용
        return next(iter(normalized.values()))

    # 우선순위 최고 소스의 값 사용
    return normalized[available[0]]
