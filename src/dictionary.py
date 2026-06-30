"""라인 사전 (line_fact v2) — append-only + revoked + conflict quarantine.

설계 원칙:
- CLOSURE_LABEL 정답을 라인 단위로 적립 (learn). append-only (덮어쓰기 없음).
- revoke: 틀린 정답 철회 (삭제 아님, revoked=True).
- quarantine: 같은 키 다른 향 충돌 시 confidence 낮춰 보류.
- 4중 가드: (1) ledger 교집합 (2) 단일성 (3) 층 일관 (4) revoked.
- 사전 단독으로 호 확정하지 않는다 — narrow 만, 확정은 pipeline.

References: A35 (화석화 방어), A65 (line_fact 테이블), A81 (확정 과장 금지).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from src.floorplan_infer import extract_line_from_ho

__all__ = ["LineFact", "LineFactDictionary"]

_LEARN_CONFIDENCE = 0.95       # CLOSURE_LABEL 정답 적립 시 기본
_QUARANTINE_CONFIDENCE = 0.3   # 충돌 보류 시 (낮춰 저장)


def _now() -> datetime:
    """현재 UTC 시각 (테스트 대체 가능)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LineFact:
    """라인 정답 단위 — (단지, 동, 라인) → (향, 타입, 신뢰도).

    append-only: direction/area_type 은 최초 learn 후 변경 안 됨.
    observations 만 누적. revoked=True 면 get → None (삭제 아님).
    """

    complex_id: str
    dong: str
    line: str
    direction: str
    area_type: str
    confidence: float = _LEARN_CONFIDENCE
    observations: int = 1
    revoked: bool = False
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


class LineFactDictionary:
    """라인 정답 사전 — append-only + revoke + quarantine + 4중 가드.

    메모리 내 저장 (DB 없음). 키 = (complex_id, dong, line).
    사전 단독으로 호 확정 불가 (narrow 만, 확정은 pipeline).
    """

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str, str], LineFact] = {}

    @staticmethod
    def _key(c: str, d: str, l: str) -> tuple[str, str, str]:
        return (c, d, l)

    def learn(
        self,
        complex_id: str,
        dong: str,
        line: str,
        direction: str,
        area_type: str,
        source: str,
    ) -> LineFact:
        """CLOSURE_LABEL 정답 적립 (append-only).

        - 키 없음/revoked → 새 LineFact (observations=1).
        - 같은 키 + 같은 향 → observations 누적.
        - 같은 키 + 다른 향 → 충돌, 기존 유지 반환 (caller: check_conflict + quarantine).
        """
        del source  # 향후 confidence 매핑용 예약
        key = self._key(complex_id, dong, line)
        existing = self._facts.get(key)
        now = _now()

        if existing is None or existing.revoked:
            fact = LineFact(
                complex_id=complex_id, dong=dong, line=line,
                direction=direction, area_type=area_type,
                confidence=_LEARN_CONFIDENCE, observations=1,
                revoked=False, created_at=now, updated_at=now,
            )
            self._facts[key] = fact
            return fact

        if existing.direction == direction:
            updated = replace(
                existing,
                observations=existing.observations + 1,
                updated_at=now,
            )
            self._facts[key] = updated
            return updated

        return existing  # 충돌: append-only 로 기존 유지

    def narrow_candidates(
        self,
        complex_id: str,
        dong: str,
        candidates: list[dict],
    ) -> list[dict]:
        """후보를 향으로 좁히기만 (없는 호 생성 불가). 4중 가드 적용.

        1. ledger 교집합 — 입력 후보만 필터, 향 불일치 제외.
        2. 단일성 — 단일 후보 시 likely=True (확정 아님).
        3. 층 일관 — floor_consistent 플래그.
        4. revoked — revoked 라인 후보 제외.

        결과는 항상 리스트 (사전 단독 호 확정 불가).
        """
        if not candidates:
            return []

        result: list[dict] = []
        for cand in candidates:
            ho = str(cand.get("ho", ""))
            line = cand.get("line") or extract_line_from_ho(ho) or ""
            cand_dir = cand.get("direction", "")
            raw_fact = self._facts.get(self._key(complex_id, dong, line))

            # Guard 4: revoked 라인 → 제외
            if raw_fact is not None and raw_fact.revoked:
                continue

            if raw_fact is None:
                # Guard 1: 사전 정보 없음 — 좁히지 못함 (유지)
                result.append({**cand, "line": line,
                                "direction_match": None, "likely": False})
                continue

            # Guard 1: 향 불일치 → 제외 (narrow)
            if cand_dir and raw_fact.direction and cand_dir != raw_fact.direction:
                continue

            result.append({
                **cand, "line": line,
                "direction_match": (cand_dir == raw_fact.direction
                                    if cand_dir else None),
                "likely": False,
            })

        # Guard 2: 단일성 — likely 부스트 (확정 아님)
        if len(result) == 1:
            result[0] = {**result[0], "likely": True}

        # Guard 3: 층 일관 플래그
        floors = {c.get("floor") for c in result
                  if c.get("floor") is not None}
        consistent = len(floors) <= 1
        for c in result:
            c["floor_consistent"] = consistent

        return result

    def revoke(self, complex_id: str, dong: str, line: str) -> bool:
        """틀린 정답 철회 (삭제 아님, revoked=True). True if 기존 존재."""
        key = self._key(complex_id, dong, line)
        existing = self._facts.get(key)
        if existing is None:
            return False
        self._facts[key] = replace(
            existing, revoked=True, updated_at=_now(),
        )
        return True

    def get(self, complex_id: str, dong: str, line: str) -> LineFact | None:
        """조회. revoked=True 면 None."""
        fact = self._facts.get(self._key(complex_id, dong, line))
        if fact is None or fact.revoked:
            return None
        return fact

    def get_all(self, complex_id: str, dong: str) -> list[LineFact]:
        """동 전체 라인 조회 (revoked 제외)."""
        return [f for f in self._facts.values()
                if f.complex_id == complex_id
                and f.dong == dong and not f.revoked]

    def check_conflict(
        self, complex_id: str, dong: str, line: str, direction: str,
    ) -> bool:
        """같은 키 다른 향 → True. 기존 없거나 향 일치 → False."""
        existing = self.get(complex_id, dong, line)
        if existing is None:
            return False
        return existing.direction != direction

    def quarantine(
        self, complex_id: str, dong: str, line: str, direction: str,
    ) -> None:
        """충돌 시 보류 — 저장하되 confidence=_QUARANTINE_CONFIDENCE."""
        key = self._key(complex_id, dong, line)
        existing = self._facts.get(key)
        now = _now()
        if existing is None:
            self._facts[key] = LineFact(
                complex_id=complex_id, dong=dong, line=line,
                direction=direction, area_type="",
                confidence=_QUARANTINE_CONFIDENCE, observations=1,
                revoked=False, created_at=now, updated_at=now,
            )
        else:
            self._facts[key] = replace(
                existing, direction=direction,
                confidence=_QUARANTINE_CONFIDENCE, updated_at=now,
            )
