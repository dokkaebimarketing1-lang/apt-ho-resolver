"""주택인허가 호별개요 ETL 테스트."""

from __future__ import annotations

import tempfile

import pytest

from src.ingest.housing_permit import (
    SEPARATOR,
    extract_area_type_stats,
    parse_file,
    parse_row,
)


class TestParseRow:
    def test_valid_row(self):
        """정상 행 파싱 — 22컬럼 pipe-delimited."""
        row = SEPARATOR.join([
            "1053100018738",  # 0: mgm_bldrgst_pk
            "1053100003401", "인천 남동구 구월동 1485번지",
            "구월아시아드선수촌2단지", "28200", "10100", "0", "1485",
            "0000", "", "", "",  # 9-11: 빈칸
            "203동",  # 12: 동명
            "9",      # 13: 층번호
            "20", "지상", "0",
            "904",    # 17: 호명칭
            "51B",    # 18: 전용면적(평형구분명)
            "", "", "20220625",
        ])
        result = parse_row(row)
        assert result is not None
        assert result["mgm_bldrgst_pk"] == "1053100018738"
        assert result["dong_name"] == "203동"
        assert result["floor"] == 9
        assert result["ho_name"] == "904"
        assert result["area_type"] == "51B"

    def test_missing_ho_name(self):
        """호명칭 없는 행 → None."""
        row = SEPARATOR.join([
            "1053100018738", "", "", "", "", "", "", "", "", "",
            "", "", "203동", "", "", "", "", "", "", "", "", "",
        ])
        assert parse_row(row) is None

    def test_empty_line(self):
        """빈 행 → None."""
        assert parse_row("") is None

    def test_too_short_line(self):
        """컬럼 부족 → None."""
        row = SEPARATOR.join(["a", "b", "c"])
        assert parse_row(row) is None

    def test_floor_not_number(self):
        """층번호가 숫자 아님 → floor=None."""
        row = SEPARATOR.join([
            "1053100018738", "", "", "", "", "", "", "", "", "",
            "", "", "203동", "N/A", "", "", "", "904", "51B", "", "", "",
        ])
        result = parse_row(row)
        assert result is not None
        assert result["floor"] is None


class TestParseFile:
    def test_parse_from_temp_file(self):
        """임시 파일로 전체 파이프라인 테스트."""
        row1 = SEPARATOR.join([
            "1053100018738", "", "", "", "", "", "", "", "", "",
            "", "", "203동", "9", "", "", "", "904", "51B", "", "", "",
        ])
        row2 = SEPARATOR.join([
            "1053100018739", "", "", "", "", "", "", "", "", "",
            "", "", "203동", "10", "", "", "", "1004", "59A", "", "", "",
        ])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write(row1 + "\n")
            f.write(row2 + "\n")
            f.write("bad,line\n")
            temp_path = f.name

        try:
            results = parse_file(temp_path)
            assert len(results) == 2
            assert results[0]["ho_name"] == "904"
            assert results[1]["ho_name"] == "1004"
        finally:
            import os
            os.unlink(temp_path)

    def test_max_rows(self):
        """max_rows 제한."""
        rows_data = []
        for i in range(10):
            row = SEPARATOR.join([
                f"PK{i}", "", "", "", "", "", "", "", "", "",
                "", "", f"{i}01동", f"{i}", "", "", "", f"{i:04d}", "84A", "", "", "",
            ])
            rows_data.append(row)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write("\n".join(rows_data) + "\n")
            temp_path = f.name

        try:
            results = parse_file(temp_path, max_rows=5)
            assert len(results) == 5
        finally:
            import os
            os.unlink(temp_path)


class TestAreaTypeStats:
    def test_stats(self):
        """평형구분명 분포."""
        rows = [
            {"area_type": "84A"},
            {"area_type": "84A"},
            {"area_type": "59B"},
            {"area_type": ""},
        ]
        stats = extract_area_type_stats(rows)
        assert stats["84A"] == 2
        assert stats["59B"] == 1
