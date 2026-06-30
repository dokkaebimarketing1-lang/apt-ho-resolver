"""건축물대장 전유부 벌크 CSV 파서 (Todo 9).

건축HUB 전유부 CSV (pipe-delimited, UTF-8, no header, 27 columns).

컬럼 매핑:
    0: mgm_bldrgst_pk
    21: 동명칭 (dong_name, e.g. "102동")
    22: 호명칭 (ho_name, e.g. "624호")
    23: 층구분코드 (20=지상)
    25: 층번호 (floor)

⚠️ area(전용면적) 없음 — 전유공용면적 API(getBrExposPubuseAreaInfo)로 별도 조회 필요.
"""

from __future__ import annotations

from typing import Any

COL_MGM_PK = 0
COL_DONG_NAME = 21
COL_HO_NAME = 22
COL_FLOOR = 25

SEPARATOR = "|"
ENCODING = "utf-8"


def parse_row(line: str) -> dict[str, Any] | None:
    """pipe-delimited 행 파싱."""
    parts = line.split(SEPARATOR)
    if len(parts) < 26:
        return None

    try:
        mgm_pk = parts[COL_MGM_PK].strip()
        dong_name = parts[COL_DONG_NAME].strip()
        ho_name = parts[COL_HO_NAME].strip()
        floor_str = parts[COL_FLOOR].strip()

        if not mgm_pk:
            return None

        floor_val: int | None = None
        if floor_str:
            try:
                floor_val = int(floor_str)
            except ValueError:
                pass

        return {
            "mgm_bldrgst_pk": mgm_pk,
            "dong_name": dong_name,
            "ho_name": ho_name,
            "floor": floor_val,
        }
    except (IndexError, ValueError):
        return None


def parse_file(filepath: str, *, max_rows: int = 0) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    count = 0
    with open(filepath, encoding=ENCODING) as f:
        for line in f:
            row = parse_row(line)
            if row:
                results.append(row)
                count += 1
                if max_rows > 0 and count >= max_rows:
                    break
    return results


__all__ = ["COL_MGM_PK", "COL_DONG_NAME", "COL_HO_NAME", "COL_FLOOR",
           "SEPARATOR", "ENCODING", "parse_row", "parse_file"]
