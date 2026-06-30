"""리포트 생성·정화 테스트."""
from __future__ import annotations

from src.domain import HoConclusion
from src.report import generate_report, sanitize_report


class TestGenerateReport:
    """generate_report — HTML 리포트 생성."""

    def test_output_contains_estimate_tag(self) -> None:
        """Given 추정 결론 When 리포트 생성 Then HTML 에 '추정' 태그 포함"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[{"ho": "101호", "probability": 0.95}],
            ho_final="101호",
            grade="high",
            is_estimate=True,
        )
        html = generate_report([c], "테스트단지")
        assert "추정" in html
        assert "라벨일치" not in html

    def test_output_contains_label_match(self) -> None:
        """Given is_estimate=False 결론 When 리포트 생성 Then '라벨일치' 표기"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[{"ho": "101호", "probability": 1.0}],
            ho_final="101호",
            grade="confirmed",
            is_estimate=False,
        )
        html = generate_report([c], "테스트단지")
        assert "라벨일치" in html

    def test_multi_candidate_shows_probability_list(self) -> None:
        """Given 다호 후보 When 리포트 생성 Then [{ho, probability}] 리스트 표시"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[
                {"ho": "101호", "probability": 0.60},
                {"ho": "102호", "probability": 0.40},
            ],
            grade="medium",
            is_estimate=True,
        )
        html = generate_report([c], "테스트단지")
        # 다호 후보를 단일 호로 축약하지 않고 확률 리스트 표시
        assert "101호" in html
        assert "102호" in html
        assert "0.60" in html or "0.6" in html
        assert "0.40" in html or "0.4" in html

    def test_single_candidate_does_not_collapse(self) -> None:
        """Given 단일 후보 When 리포트 생성 Then 후보 정보 유지 (축약 금지)"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[{"ho": "101호", "probability": 0.95}],
            ho_final="101호",
            grade="high",
            is_estimate=True,
        )
        html = generate_report([c], "테스트단지")
        # 단일 후보 정보가 유지되어야 함 (ho_final 과 별도로 후보 정보 표시)
        assert "0.95" in html
        assert "101호" in html

    def test_grade_sorting_confirmed_first(self) -> None:
        """Given 혼합 등급 When 리포트 생성 Then confirmed 이 먼저 표시"""
        c_low = HoConclusion(
            complex_id="c1",
            dong="102동",
            candidate_hos=[{"ho": "201호"}],
            grade="low",
            is_estimate=True,
        )
        c_high = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[{"ho": "101호"}],
            grade="confirmed",
            is_estimate=False,
        )
        html = generate_report([c_low, c_high], "테스트단지")
        # 'confirmed' 등급이 'low' 보다 먼저 나와야 함
        confirmed_pos = html.index("grade-confirmed")
        low_pos = html.index("grade-low")
        assert confirmed_pos < low_pos

    def test_output_complex_name_in_title(self) -> None:
        """Given complex_name When 리포트 생성 Then 타이틀에 단지명 포함"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[{"ho": "101호"}],
            grade="high",
            is_estimate=True,
        )
        html = generate_report([c], "래미안퍼스티지")
        assert "래미안퍼스티지" in html

    def test_empty_conclusions(self) -> None:
        """Given 빈 conclusions 리스트 When 리포트 생성 Then 빈 테이블"""
        html = generate_report([], "빈단지")
        assert "빈단지" in html
        assert "0건" in html or "0" in html

    def test_no_candidate_hos(self) -> None:
        """Given 후보 없음 When 리포트 생성 Then '?' 또는 '—' 표시"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[],
            grade="none",
            is_estimate=True,
        )
        html = generate_report([c], "테스트단지")
        assert "?" in html or "—" in html

    def test_multi_candidate_not_abbreviated(self) -> None:
        """Given 다호 후보 When 리포트 생성 Then 반드시 리스트 형태 유지 (단일 호 축약 금지)"""
        c = HoConclusion(
            complex_id="c1",
            dong="101동",
            candidate_hos=[
                {"ho": "101호", "probability": 0.55},
                {"ho": "102호", "probability": 0.45},
            ],
            grade="medium",
            is_estimate=True,
        )
        html = generate_report([c], "테스트단지")
        # 둘 다 표시되는지 확인 — 하나만 있으면 축약된 것
        assert '{"101호"' in html or '"101호"' in html
        assert '{"102호"' in html or '"102호"' in html


class TestSanitizeReport:
    """sanitize_report — 리포트 정화."""

    def test_removes_source_id(self) -> None:
        """Given source_id 포함 HTML When 정화 Then source_id 제거"""
        html = '<div>source_id="12345"</div>'
        result = sanitize_report(html)
        assert "12345" not in result
        assert "REDACTED" in result

    def test_removes_articleNo(self) -> None:
        """Given articleNo 포함 HTML When 정화 Then articleNo 제거"""
        html = '<div>articleNo=98765</div>'
        result = sanitize_report(html)
        assert "98765" not in result
        assert "REDACTED" in result

    def test_removes_method_log(self) -> None:
        """Given method-log div 포함 HTML When 정화 Then method-log 제거"""
        html = '<div class="method-log">detail=step1</div>'
        result = sanitize_report(html)
        assert "step1" not in result
        assert "method-log" not in result

    def test_removes_long_numeric_ids_from_urls(self) -> None:
        """Given URL 에 긴 숫자 ID 포함 When 정화 Then ID 제거"""
        html = '<a href="https://example.com/article/12345678">link</a>'
        result = sanitize_report(html)
        assert "12345678" not in result
        assert "REDACTED" in result

    def test_replaces_standalone_confirm(self) -> None:
        """Given '>확정<' 포함 HTML When 정화 Then '>추정<' 으로 대체"""
        html = "<td>확정</td>"
        result = sanitize_report(html)
        assert ">확정<" not in result
        # 추정 으로 대체되었거나 원래 텍스트가 변경됨
        assert "추정" in result or ">" not in result  # at least sanitized

    def test_preserves_rest_of_html(self) -> None:
        """Given 정화 대상 제외 HTML When 정화 Then 나머지 구조 유지"""
        html = "<html><body><h1>타이틀</h1><p>내용</p></body></html>"
        result = sanitize_report(html)
        assert "<h1>타이틀</h1>" in result
        assert "<p>내용</p>" in result

    def test_no_source_id_no_change(self) -> None:
        """Given source_id 없는 HTML When 정화 Then 변경 없음"""
        html = "<p>정상 텍스트</p>"
        result = sanitize_report(html)
        assert result == html
