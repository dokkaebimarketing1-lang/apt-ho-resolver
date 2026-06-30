"""공시가격 ETL 테스트."""

from __future__ import annotations

import tempfile

import pytest

from src.ingest.public_price import SEPARATOR, parse_file, parse_row


class TestParseRow:
    def test_valid_row(self):
        """정상 행 파싱."""
        row = SEPARATOR.join([
            "1056183078", "2", "집합", "4", "전유부",
            "인천 미추홀구 학익동 719번지", "인천 미추홀구 소성로 120",
            "동아,풍림아파트", "28177", "10300", "0", "0719", "0000",
            "", "", "", "0", "281773151009", "10302", "0", "120",
            "", "20090101", "208000000", "20220625",
        ])
        result = parse_row(row)
        assert result is not None
        assert result["mgm_bldrgst_pk"] == "1056183078"
        assert result["building_name"] == "동아,풍림아파트"
        assert result["public_price"] == 208000000

    def test_empty_pk(self):
        """PK 없는 행 → None."""
        row = SEPARATOR.join([""] * 25)
        assert parse_row(row) is None

    def test_too_short(self):
        """컬럼 부족 → None."""
        assert parse_row("a|b|c") is None


class TestParseFile:
    def test_parse_temp_file(self):
        """임시 파일 파싱."""
        row = SEPARATOR.join([
            "1056183078", "2", "집합", "4", "전유부",
            "주소1", "주소2", "테스트아파트", "28177", "10300",
            "0", "0719", "0000", "", "", "", "0", "PK1", "10302",
            "0", "120", "", "20090101", "150000000", "20220625",
        ])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write(row + "\n")
            temp_path = f.name
        try:
            results = parse_file(temp_path)
            assert len(results) == 1
            assert results[0]["public_price"] == 150000000
        finally:
            import os
            os.unlink(temp_path)
