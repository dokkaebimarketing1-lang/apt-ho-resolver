"""리포트 생성·정화(Sanitizer) — 최종 호 결론 → HTML 가시화 + 개인정보 제거.

핵심 규칙:
- 모든 호 결론은 "추정" 표기 필수 (is_estimate=True 가 기본).
- 다호 후보는 절대 단일 호로 축약하지 않고 [{ho, probability}] 리스트로 표시.
- "확정" 단독 표기 금지 — 항상 "추정" 또는 "라벨일치" 맥락으로.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain import HoConclusion

# 등급 정렬 우선순위 (높을수록 위에 표시)
_GRADE_ORDER: dict[str, int] = {
    "confirmed": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "none": 4,
}

# 호(일련번호) 리스트 문자열 포맷 — candidate_hos 의 각 항목은 {"ho": str, "probability": float}
_CANDIDATE_TEMPLATE = '<span class="candidate-list">[{candidates}]</span>'


def _grade_sort_key(c: HoConclusion) -> tuple[int, str]:
    """등급순 정렬 키 — 등급 우선순위 + 동명 오름차순."""
    order = _GRADE_ORDER.get(c.grade, 99)
    return (order, c.dong or "")


def _format_candidates(candidate_hos: list[dict[str, Any]]) -> str:
    """후보 호 리스트를 HTML 문자열로 포맷.

    다호 후보가 있으면 [{ho, probability}] 형태로 표시.
    단일 후보여도 포맷은 동일하게 유지 (축약 금지).
    """
    parts: list[str] = []
    for cand in candidate_hos:
        ho = cand.get("ho", "?")
        prob = cand.get("probability")
        if prob is not None:
            parts.append(f'{{"{ho}", {prob:.2f}}}')
        else:
            parts.append(f'{{"{ho}"}}')
    return ", ".join(parts)


def _escape_html(text: str) -> str:
    """HTML 특수문자 이스케이프."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_report(
    conclusions: list[HoConclusion],
    complex_name: str,
) -> str:
    """HTML 리포트 생성 — 등급순 정렬, 추정 표기, 다호 후보 확률 리스트 표시.

    Args:
        conclusions: 최종 호 결론 리스트.
        complex_name: 단지명.

    Returns:
        완전한 HTML 문서 문자열.
    """
    rows: list[str] = []
    sorted_conclusions = sorted(conclusions, key=_grade_sort_key)

    for c in sorted_conclusions:
        dong = _escape_html(c.dong or "?")
        grade = _escape_html(c.grade)
        is_estimate = c.is_estimate
        candidate_hos = c.candidate_hos
        ho_final = c.ho_final

        # 추정 표기
        if is_estimate:
            estimate_label = "추정"
        else:
            estimate_label = "라벨일치"

        # 최종호 표시
        if ho_final and candidate_hos:
            final_ho = _escape_html(ho_final)
        elif candidate_hos:
            final_ho = _format_candidates(candidate_hos)
        else:
            final_ho = "?"

        # 후보 리스트 — 다호 후보 단일 축약 금지
        if len(candidate_hos) > 1:
            candidates_html = _format_candidates(candidate_hos)
        elif len(candidate_hos) == 1:
            # 단일 후보여도 같은 정보를 표시 (포맷 일관성)
            candidates_html = _format_candidates(candidate_hos)
        else:
            candidates_html = "—"

        row = (
            f"<tr>"
            f"<td>{dong}</td>"
            f"<td>{final_ho}</td>"
            f"<td class=\"grade-{grade}\">{grade}</td>"
            f"<td>{candidates_html}</td>"
            f"<td class=\"estimate-tag\">{estimate_label}</td>"
            f"</tr>"
        )
        rows.append(row)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{_escape_html(complex_name)} 호수 추정 리포트</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
h1 {{ font-size: 1.5rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
th {{ background: #f5f5f5; }}
.grade-confirmed {{ color: #1a7d1a; font-weight: bold; }}
.grade-high {{ color: #2b6cb0; }}
.grade-medium {{ color: #b7791f; }}
.grade-low {{ color: #9b2c2c; }}
.estimate-tag {{ font-size: 0.85rem; color: #666; }}
.candidate-list {{ font-family: monospace; font-size: 0.9rem; }}
.footer {{ margin-top: 1rem; font-size: 0.8rem; color: #888; }}
</style>
</head>
<body>
<h1>{_escape_html(complex_name)} — 호수 추정 리포트</h1>
<p>생성일: {now} | 총 {len(rows)}건</p>
<table>
<thead>
<tr><th>동</th><th>최종 호(추정)</th><th>등급</th><th>후보 리스트</th><th>비고</th></tr>
</thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<p class="footer">※ 모든 호는 추정치입니다. 정확한 호는 공부(등기부등본)를 확인하세요.</p>
</body>
</html>"""
    return html


def sanitize_report(html: str) -> str:
    """리포트에서 개인정보·내부 메타데이터 제거.

    제거 대상:
    - source_id (게시물 ID)
    - articleNo (게시물 번호)
    - method_log (추론 상세 로그)
    - provenance.url 중 식별자 부분

    Args:
        html: 원본 HTML 리포트.

    Returns:
        정화된 HTML 문자열.
    """
    import re

    # 1. source_id 패턴 제거 (숫자 식별자)
    html = re.sub(
        r'\bsource_id["\']?\s*[:=]\s*["\']?\d+["\']?',
        'source_id="[REDACTED]"',
        html,
    )

    # 2. articleNo 패턴 제거
    html = re.sub(
        r'\barticleNo["\']?\s*[:=]\s*["\']?\d+["\']?',
        'articleNo="[REDACTED]"',
        html,
    )

    # 3. method_log 블록 제거
    html = re.sub(
        r'<div class="method-log">.*?</div>',
        '',
        html,
        flags=re.DOTALL,
    )

    # 4. URL 에서 식별자 제거 (숫자로 끝나는 path segment)
    html = re.sub(
        r'(https?://[^"\s<>]+?)/(\d{5,})(["\s<>])',
        r'\1/[REDACTED]\3',
        html,
    )

    # 5. "확정" 단독 표기를 "추정" 으로 대체 (안전장치)
    html = html.replace(">확정<", ">추정<")

    return html
