"""주택인허가 호별개요 벌크파일(pipe-delimited) 파서 (Todo 8).

건축HUB 주택인허가 호별개요 CSV (pipe-delimited, UTF-8, no header, 22 columns).

컬럼 매핑:
    0: mgm_bldrgst_pk
    12: 동명
    13: 층번호 (flrNo)
    17: 호명칭 (hoNm)
    18: 전용면적 (pngtypGbNm, 평형구분명 e.g. "51B")
"""

from __future__ import annotations

from typing import Any


# 실제 컬럼 인덱스
COL_MGM_PK = 0
COL_DONG_NAME = 12
COL_FLOOR = 13
COL_HO_NAME = 17
COL_AREA_TYPE = 18  # 평형구분명 pngtypGbNm (not actual area m²!)

# CSV 파일 구분자 및 인코딩
SEPARATOR = "|"
ENCODING = "utf-8"


def parse_row(line: str) -> dict[str, Any] | None:
    """pipe-delimited 행을 파싱하여 필드 추출.

    Args:
        line: pipe-delimited CSV 행 (예: "1053100018738|1053100003401|...|904|51B|...")

    Returns:
        {
            "mgm_bldrgst_pk": str,
            "dong_name": str,
            "floor": int | None,
            "ho_name": str,
            "area_type": str,  # 평형구분명
        }
        또는 파싱 실패 시 None.
    """
    parts = line.split(SEPARATOR)

    if len(parts) < 19:
        return None

    try:
        mgm_pk = parts[COL_MGM_PK].strip()
        dong_name = parts[COL_DONG_NAME].strip()
        floor_str = parts[COL_FLOOR].strip()
        ho_name = parts[COL_HO_NAME].strip()
        area_type = parts[COL_AREA_TYPE].strip()

        if not mgm_pk or not ho_name:
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
            "floor": floor_val,
            "ho_name": ho_name,
            "area_type": area_type,
        }
    except (IndexError, ValueError):
        return None


def parse_file(filepath: str, *, max_rows: int = 0) -> list[dict[str, Any]]:
    """파일 전체 파싱 (또는 max_rows개만).

    Args:
        filepath: CSV 파일 경로.
        max_rows: 최대 행 수 (0 = 전체).

    Returns:
        파싱된 행 리스트.
    """
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


def extract_area_type_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    """평형구분명 분포 통계.

    Returns:
        {area_type: count, ...}
    """
    stats: dict[str, int] = {}
    for row in rows:
        at = row["area_type"]
        if at:
            stats[at] = stats.get(at, 0) + 1
    return stats


__all__ = [
    "COL_MGM_PK", "COL_DONG_NAME", "COL_FLOOR", "COL_HO_NAME", "COL_AREA_TYPE",
    "SEPARATOR", "ENCODING",
    "parse_row", "parse_file", "extract_area_type_stats",
]
