"""집합건물호 ETL 테스트 (Todo 7)."""

from __future__ import annotations

import tempfile

from src.ingest.collective_building import parse_file, parse_row


class TestParseRow:
    def test_valid_row(self):
        """정상 행 — pipe-delimited."""
        row = "서울 강남구 역삼동 123|101동|1503호|15|84.5|"
        result = parse_row(row)
        assert result is not None
        assert result["jibun"] == "서울 강남구 역삼동 123"
        assert result["dong"] == "101동"
        assert result["ho"] == "1503호"
        assert result["floor"] == 15
        assert result["area"] == 84.5

    def test_missing_jibun(self):
        """지번 없음 → None."""
        row = "|101동|1503호|15|84.5"
        assert parse_row(row) is None

    def test_empty_line(self):
        assert parse_row("") is None

    def test_short_line(self):
        assert parse_row("a|b|c") is None

    def test_no_floor(self):
        """층 번호 없음 → floor=None."""
        row = "서울 강남구|101동|1503호||84.5"
        result = parse_row(row)
        assert result is not None
        assert result["floor"] is None


class TestParseFile:
    def test_parse_temp_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8",
        ) as f:
            f.write("서울 강남구|101동|1503호|15|84.5\n")
            f.write("서울 강남구|101동|1504호|15|115.0\n")
            temp_path = f.name
        try:
            results = parse_file(temp_path)
            assert len(results) == 2
            assert results[0]["ho"] == "1503호"
            assert results[1]["area"] == 115.0
        finally:
            import os
            os.unlink(temp_path)
