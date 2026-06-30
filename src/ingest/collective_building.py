"""집합건물호 다운로더 — vworld.kr TXT 수집 (Todo 7).

vworld.kr에서 집합건물호 TXT 다운로드.
TXT 형식 파싱 → (지번, 동, 호, 층, 전용면적) 추출.
"""

from __future__ import annotations

from typing import Any


def parse_row(line: str) -> dict[str, Any] | None:
    """집합건물호 TXT 행 파싱.

    vworld.kr 집합건물호 TXT 형식:
    지번주소|동명|호명|층|전용면적|...

    Args:
        line: TXT 행.

    Returns:
        {"jibun": str, "dong": str, "ho": str, "floor": int|None, "area": float|None}
    """
    parts = line.strip().split("|")
    if len(parts) < 5:
        return None

    jibun = parts[0].strip()
    dong = parts[1].strip()
    ho = parts[2].strip()
    floor_str = parts[3].strip()
    area_str = parts[4].strip()

    if not jibun or not ho:
        return None

    floor_val: int | None = None
    if floor_str:
        try:
            floor_val = int(floor_str)
        except ValueError:
            pass

    area_val: float | None = None
    if area_str:
        try:
            area_val = float(area_str)
        except ValueError:
            pass

    return {
        "jibun": jibun,
        "dong": dong,
        "ho": ho,
        "floor": floor_val,
        "area": area_val,
    }


def parse_file(filepath: str, *, max_rows: int = 0) -> list[dict[str, Any]]:
    """TXT 파일 전체 파싱."""
    results: list[dict[str, Any]] = []
    count = 0
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            row = parse_row(line)
            if row:
                results.append(row)
                count += 1
                if max_rows > 0 and count >= max_rows:
                    break
    return results


def download_collective_building(
    url: str = "https://vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30582",
) -> bytes:
    """vworld.kr에서 집합건물호 데이터 다운로드.

    실제 다운로드는 httpx로 수행.
    테스트에서는 mock으로 대체.

    Args:
        url: vworld.kr 다운로드 URL.

    Returns:
        다운로드된 바이트 데이터.
    """
    try:
        import httpx
        resp = httpx.get(url, timeout=300, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except ImportError:
        raise RuntimeError("httpx not available")


__all__ = ["parse_row", "parse_file", "download_collective_building"]
