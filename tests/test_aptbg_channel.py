"""아파트백과 채널 단위 테스트 — mock 응답 사용."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest

from src.channels.aptbg import (
    SAMPLE_COMPLEXES,
    AptbgChannel,
    FloorPlanImage,
    _build_search_url,
    _infer_plan_type,
    _parse_floor_plans,
    get_aptbg_id,
)


# ── 픽스처 — mock HTML ────────────────────────────────────────────────────

MOCK_FLOORPLAN_HTML_MAIN = """<!DOCTYPE html>
<html>
<head><title>래미안원베일리 평면도</title></head>
<body>
<div class="content">
<h1>래미안원베일리 평면도</h1>
<div class="floorplan-gallery">
<div class="item">
<img src="https://img.aptbg.com/1000001/floorplan_01.jpg" alt="전용84A">
<span class="info">전용 84A (33평형)</span>
</div>
<div class="item">
<img src="https://img.aptbg.com/1000001/floorplan_02.jpg" alt="전용84B">
<span class="info">전용 84B (33평형)</span>
</div>
<div class="item">
<img src="https://img.aptbg.com/1000001/floorplan_03.jpg" alt="전용59A">
<span class="info">전용 59A (25평형)</span>
</div>
</div>
</div>
</body>
</html>
"""

MOCK_FLOORPLAN_HTML_BAY = """<!DOCTYPE html>
<html>
<head><title>래미안퍼스티지 배치도</title></head>
<body>
<div class="content">
<h1>래미안퍼스티지 배치도</h1>
<div class="floorplan-gallery">
<div class="item">
<img src="https://img.aptbg.com/1000002/bay_01.jpg" alt="84A 타입 배치">
<span class="info">84A 타입 배치도</span>
</div>
<div class="item">
<img src="https://img.aptbg.com/1000002/bay_02.jpg" alt="84B 타입 배치">
<span class="info">84B 타입 배치도</span>
</div>
</div>
</div>
</body>
</html>
"""

MOCK_FLOORPLAN_HTML_ALT = """<!DOCTYPE html>
<html>
<body>
<div class="floor_plan_list">
<div class="unit">
<img src="/images/1000003/floorplan_01.jpg" alt="전용84A">
</div>
<div class="unit">
<img src="/images/1000003/floorplan_02.jpg" alt="전용84B">
</div>
</div>
</body>
</html>
"""

MOCK_EMPTY_HTML = """<!DOCTYPE html>
<html>
<body>
<p>정보가 없습니다.</p>
</body>
</html>
"""

MOCK_VALID_FIXTURE = [
    {
        "image_url": "https://img.aptbg.com/1000001/floorplan_01.jpg",
        "caption": "전용 84A (33평형)",
        "plan_type": "평면도",
        "aptbg_id": "1000001",
    },
    {
        "image_url": "https://img.aptbg.com/1000001/floorplan_02.jpg",
        "caption": "전용 84B (33평형)",
        "plan_type": "평면도",
        "aptbg_id": "1000001",
    },
]


# ── 테스트: 상수 ───────────────────────────────────────────────────────────


class TestConstants:
    """SAMPLE_COMPLEXES 및 상수 검증."""

    def test_sample_complexes_count(self) -> None:
        """Given SAMPLE_COMPLEXES When 확인 Then 10개 단지"""
        assert len(SAMPLE_COMPLEXES) == 10

    def test_sample_complexes_have_required_keys(self) -> None:
        """Given 모든 샘플 단지 When 확인 Then 'address' 와 'aptbg_id' 키"""
        for name, info in SAMPLE_COMPLEXES.items():
            assert "address" in info, f"{name}: address 누락"
            assert "aptbg_id" in info, f"{name}: aptbg_id 누락"
            assert isinstance(info["address"], str), f"{name}: address 는 str"
            assert isinstance(info["aptbg_id"], str), f"{name}: aptbg_id 는 str"
            assert len(info["address"]) > 0, f"{name}: address 비어있음"
            assert len(info["aptbg_id"]) > 0, f"{name}: aptbg_id 비어있음"

    def test_aptbg_id_lookup(self) -> None:
        """Given 등록 단지명 When get_aptbg_id Then ID 반환"""
        aid = get_aptbg_id("래미안원베일리")
        assert aid == "1000001"

    def test_aptbg_id_lookup_unknown(self) -> None:
        """Given 미등록 단지명 When get_aptbg_id Then None"""
        assert get_aptbg_id("존재하지않는단지") is None

    def test_aptbg_id_lookup_empty(self) -> None:
        """Given 빈 문자열 When get_aptbg_id Then None"""
        assert get_aptbg_id("") is None


# ── 테스트: URL 생성 ──────────────────────────────────────────────────────


class TestBuildSearchUrl:
    """_build_search_url 검증."""

    def test_known_complex_returns_detail_url(self) -> None:
        """Given 등록 단지 When _build_search_url Then 상세 URL"""
        url = _build_search_url("래미안원베일리")
        assert url.startswith("https://aptbg.com/complex/")
        assert "1000001" in url

    def test_unknown_complex_returns_search_url(self) -> None:
        """Given 미등록 단지 When _build_search_url Then 검색 URL"""
        url = _build_search_url("테스트아파트")
        assert url.startswith("https://aptbg.com/search?q=")
        assert "%ED%85%8C%EC%8A%A4%ED%8A%B8%EC%95%84%ED%8C%8C%ED%8A%B8" in url
        assert url.count("q=") == 1

    def test_with_address(self) -> None:
        """Given 단지명+주소 When _build_search_url Then 주소 포함 검색 URL"""
        url = _build_search_url("래미안", "서울시 서초구")
        assert "%EB%9E%98%EB%AF%B8%EC%95%88" in url  # URL-encoded "래미안"
        assert "%EC%84%9C%EC%9A%B8" in url  # URL-encoded "서울"
        assert "%20" in url  # 공백 인코딩


# ── 테스트: 유형 추론 ─────────────────────────────────────────────────────


class TestInferPlanType:
    """_infer_plan_type 검증."""

    def test_평면도_default(self) -> None:
        """Given 일반 평면도 캡션 When _infer_plan_type Then '평면도'"""
        assert _infer_plan_type("전용84A", "") == "평면도"

    def test_배치도_from_caption(self) -> None:
        """Given '배치' 포함 캡션 When _infer_plan_type Then '배치도'"""
        assert _infer_plan_type("84A 타입 배치도", "") == "배치도"

    def test_배치도_from_url(self) -> None:
        """Given 'bay' 포함 URL When _infer_plan_type Then '배치도'"""
        assert _infer_plan_type("일반", "https://aptbg.com/bay_01.jpg") == "배치도"


# ── 테스트: HTML 파싱 ─────────────────────────────────────────────────────


class TestParseFloorPlans:
    """_parse_floor_plans 검증 — 주력 gallery 구조."""

    def test_parse_main_structure(self) -> None:
        """Given .floorplan-gallery HTML When _parse_floor_plans Then 3개 이미지"""
        results = _parse_floor_plans(MOCK_FLOORPLAN_HTML_MAIN, "1000001")
        assert len(results) == 3
        assert results[0]["image_url"] == "https://img.aptbg.com/1000001/floorplan_01.jpg"
        assert results[0]["caption"] == "전용 84A (33평형)"
        assert results[0]["plan_type"] == "평면도"
        assert results[0]["aptbg_id"] == "1000001"

    def test_parse_bay_images(self) -> None:
        """Given 배치도 HTML When _parse_floor_plans Then plan_type='배치도'"""
        results = _parse_floor_plans(MOCK_FLOORPLAN_HTML_BAY, "1000002")
        assert len(results) == 2
        assert results[0]["plan_type"] == "배치도"
        assert "bay_01" in results[0]["image_url"]

    def test_parse_alt_structure_with_relative_url(self) -> None:
        """Given .floor_plan_list (상대 URL) When _parse_floor_plans Then 절대 URL 변환"""
        results = _parse_floor_plans(MOCK_FLOORPLAN_HTML_ALT, "1000003")
        assert len(results) == 2
        assert results[0]["image_url"].startswith("https://aptbg.com/")
        assert "1000003" in results[0]["image_url"]

    def test_parse_empty_html(self) -> None:
        """Given 이미지 없는 HTML When _parse_floor_plans Then 빈 리스트"""
        assert _parse_floor_plans(MOCK_EMPTY_HTML, "1000001") == []

    def test_parse_empty_string(self) -> None:
        """Given 빈 문자열 When _parse_floor_plans Then 빈 리스트"""
        assert _parse_floor_plans("", "1000001") == []


# ── 테스트: AptbgChannel ──────────────────────────────────────────────────


class TestAptbgChannelCollect:
    """AptbgChannel.collect() — HTTP mock 사용."""

    def test_collect_with_mock_http(self) -> None:
        """Given mock HTTP 응답 When collect Then 이미지 URL 리스트 반환"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_FLOORPLAN_HTML_MAIN)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안원베일리"})
        assert len(results) == 3
        assert results[0]["image_url"].startswith("https://")
        assert results[0]["aptbg_id"] == "1000001"

    def test_collect_with_bay_images(self) -> None:
        """Given mock 배치도 응답 When collect Then 배치도 URL 리스트"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_FLOORPLAN_HTML_BAY)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안퍼스티지"})
        assert len(results) == 2
        assert all(r["plan_type"] == "배치도" for r in results)

    def test_collect_http_error_returns_empty(self) -> None:
        """Given HTTP 500 응답 When collect Then 빈 리스트"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안원베일리"})
        assert results == []

    def test_collect_http_404_returns_empty(self) -> None:
        """Given HTTP 404 응답 When collect Then 빈 리스트"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안원베일리"})
        assert results == []

    def test_collect_timeout_returns_empty(self) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안원베일리"})
        assert results == []

    def test_collect_alt_structure(self) -> None:
        """Given 보조 HTML 구조 When collect Then 이미지 URL 리스트"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_FLOORPLAN_HTML_ALT)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "래미안리더스원"})
        assert len(results) == 2
        assert all(r["image_url"].startswith("https://aptbg.com/") for r in results)

    def test_channel_attributes(self) -> None:
        """Given AptbgChannel 인스턴스 When 확인 Then channel_name/reliability"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_EMPTY_HTML)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        assert channel.channel_name == "aptbg"
        assert channel.reliability == 0.95
        assert isinstance(channel.channel_name, str)
        assert isinstance(channel.reliability, float)

    def test_collect_unknown_complex(self) -> None:
        """Given 미등록 단지 When collect Then 빈 리스트 또는 검색 결과"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "search" in str(request.url) or "q=" in str(request.url)
            return httpx.Response(200, text=MOCK_EMPTY_HTML)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        results = channel.collect({"complex_name": "존재하지않는단지"})
        assert results == []


class TestAptbgChannelFixture:
    """AptbgChannel — fixture 모드."""

    def test_load_valid_fixture(self) -> None:
        """Given 유효한 JSON 픽스처 When collect Then 픽스처 데이터 반환"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump(MOCK_VALID_FIXTURE, f)
            fixture_path = f.name

        try:
            channel = AptbgChannel(fixture_path=fixture_path)
            results = channel.collect({"complex_name": "래미안원베일리"})
            assert len(results) == 2
            assert results[0]["image_url"] == MOCK_VALID_FIXTURE[0]["image_url"]
            assert results[0]["caption"] == MOCK_VALID_FIXTURE[0]["caption"]
        finally:
            os.unlink(fixture_path)

    def test_fixture_file_not_found(self) -> None:
        """Given 존재하지 않는 픽스처 경로 When collect Then 빈 리스트"""
        channel = AptbgChannel(fixture_path="/nonexistent/path/fixture.json")
        results = channel.collect({"complex_name": "래미안원베일리"})
        assert results == []

    def test_fixture_invalid_json(self) -> None:
        """Given 잘못된 JSON 픽스처 When collect Then 빈 리스트"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            f.write("not valid json")
            fixture_path = f.name

        try:
            channel = AptbgChannel(fixture_path=fixture_path)
            results = channel.collect({"complex_name": "래미안원베일리"})
            assert results == []
        finally:
            os.unlink(fixture_path)

    def test_fixture_wrong_type(self) -> None:
        """Given dict 픽스처(리스트 아님) When collect Then 빈 리스트"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"key": "value"}, f)
            fixture_path = f.name

        try:
            channel = AptbgChannel(fixture_path=fixture_path)
            results = channel.collect({"complex_name": "래미안원베일리"})
            assert results == []
        finally:
            os.unlink(fixture_path)


class TestAptbgChannelSupported:
    """AptbgChannel.supported_complexes()."""

    def test_supported_complexes(self) -> None:
        """Given 채널 인스턴스 When supported_complexes Then 10개 단지명"""
        channel = AptbgChannel()
        names = channel.supported_complexes()
        assert len(names) == 10
        assert "래미안원베일리" in names
        assert "반포자이" in names


# ── 테스트: Protocol 호환성 ────────────────────────────────────────────────


class TestChannelCollectorProtocol:
    """ChannelCollector Protocol 준수 검증."""

    def test_isinstance_channel_collector(self) -> None:
        """Given AptbgChannel When isinstance ChannelCollector 체크 Then True"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_EMPTY_HTML)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        # Protocol 은 isinstance() 가 아니라 structural subtyping 이지만,
        # Protocol 클래스로 isinstance 체크 가능
        from src.channels import ChannelCollector
        assert isinstance(channel, ChannelCollector)

    def test_protocol_attributes_exist(self) -> None:
        """Given AptbgChannel When Protocol attribute 확인 Then 존재"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_EMPTY_HTML)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        assert hasattr(channel, "channel_name")
        assert hasattr(channel, "reliability")
        assert hasattr(channel, "collect")

    def test_collect_signature_compatible(self) -> None:
        """Given AptbgChannel.collect When query dict 전달 Then 작동"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=MOCK_FLOORPLAN_HTML_MAIN)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        channel = AptbgChannel(http_client=client)

        # Protocol 의 collect(query: dict) 호환
        results = channel.collect({"complex_name": "래미안원베일리"})
        assert len(results) > 0


# ── 테스트: FloorPlanImage ───────────────────────────────────────────────


class TestFloorPlanImage:
    """FloorPlanImage 데이터 클래스."""

    def test_create_floor_plan_image(self) -> None:
        """Given 유효한 필드 When FloorPlanImage 생성 Then 정상"""
        fp = FloorPlanImage(
            image_url="https://img.aptbg.com/1/img.jpg",
            caption="전용84A",
            plan_type="평면도",
            aptbg_id="1000001",
        )
        assert fp.image_url == "https://img.aptbg.com/1/img.jpg"
        assert fp.caption == "전용84A"
        assert fp.plan_type == "평면도"
        assert fp.aptbg_id == "1000001"

    def test_floor_plan_image_is_frozen(self) -> None:
        """Given FloorPlanImage When 속성 변경 시도 Then FrozenInstanceError"""
        fp = FloorPlanImage(
            image_url="https://img.aptbg.com/1/img.jpg",
            caption="전용84A",
            plan_type="평면도",
            aptbg_id="1000001",
        )
        with pytest.raises(AttributeError):
            fp.image_url = "https://changed.com/img.jpg"  # type: ignore[misc]
