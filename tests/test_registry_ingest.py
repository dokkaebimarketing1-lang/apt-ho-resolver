"""전유부 ETL 테스트."""

from __future__ import annotations

import tempfile

from src.ingest.building_registry import SEPARATOR, parse_file, parse_row


class TestParseRow:
    def test_valid_row(self):
        """정상 행 — 27컬럼 pipe-delimited."""
        row = SEPARATOR.join([
            "1002129933", "2", "집합", "4", "전유부",
            "서울 종로구 경운동 89-4번지", "서울 종로구 삼일대로 461",
            "운현궁 에스케이 허브", "11110", "13400", "0", "0089",
            "0004", "", "", "", "111102100001", "13402", "0", "461",
            "", "102동", "624호", "20", "지상", "6", "20220813",
        ])
        result = parse_row(row)
        assert result is not None
        assert result["mgm_bldrgst_pk"] == "1002129933"
        assert result["dong_name"] == "102동"
        assert result["ho_name"] == "624호"
        assert result["floor"] == 6

    def test_short_line(self):
        assert parse_row("a|b|c") is None


class TestParseFile:
    def test_temp_file(self):
        row = SEPARATOR.join([
            "1002129933", "2", "집합", "4", "전유부",
            "주소", "도로명", "건물명", "11110", "13400", "0",
            "0089", "0004", "", "", "", "PK1", "13402", "0", "461",
            "", "101동", "1503호", "20", "지상", "15", "20220813",
        ])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write(row + "\n")
            temp_path = f.name
        try:
            results = parse_file(temp_path)
            assert len(results) == 1
            assert results[0]["dong_name"] == "101동"
        finally:
            import os
            os.unlink(temp_path)
