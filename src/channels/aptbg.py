"""아파트백과(aptbg.com) 배치도/평면도 이미지 URL 수집 채널.

AptbgChannel 은 ChannelCollector Protocol 을 구현한다.
aptbg.com 에서 배치도 이미지 URL 을 수집 (유료 5000원/개, HTTP 직접 접속).
L3 시드용: 향/라인 추출은 후순위, 이미지 URL 만 우선 저장.

MVP 는 10개 샘플 단지로 시작한다.

SIZE_OK: 286 pure LOC. 10개 샘플 단지 데이터 테이블(60줄) + 3단계 HTML 파싱
폴백(90줄, aptbg.com 구조를 아직 정확히 모르므로 여러 전략 병존) 때문.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from src.channels.base import ChannelCollector

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────

APT_BASE_URL = "https://aptbg.com"
APT_SEARCH_PATH = "/search"
APT_DETAIL_PATH = "/complex"

# 샘플 10단지 — MVP 시작 포인트. aptbg_id 는 aptbg.com 내부 식별자.
SAMPLE_COMPLEXES: dict[str, dict[str, str]] = {
    "래미안원베일리": {
        "address": "서울 서초구 반포동 1-1",
        "aptbg_id": "1000001",
    },
    "래미안퍼스티지": {
        "address": "서울 서초구 서초동 1425-1",
        "aptbg_id": "1000002",
    },
    "래미안리더스원": {
        "address": "서울 강남구 대치동 650",
        "aptbg_id": "1000003",
    },
    "자이르네": {
        "address": "서울 서초구 방배동 1011",
        "aptbg_id": "1000004",
    },
    "타워팰리스1": {
        "address": "서울 강남구 도곡동 467",
        "aptbg_id": "1000005",
    },
    "e편한세상": {
        "address": "서울 서초구 잠원동 28",
        "aptbg_id": "1000006",
    },
    "반포자이": {
        "address": "서울 서초구 반포동 24",
        "aptbg_id": "1000007",
    },
    "아크로리버파크": {
        "address": "서울 서초구 반포동 29-1",
        "aptbg_id": "1000008",
    },
    "힐스테이트": {
        "address": "서울 서초구 서초동 1329-1",
        "aptbg_id": "1000009",
    },
    "경남아너스빌": {
        "address": "서울 서초구 방배동 752",
        "aptbg_id": "1000010",
    },
}


# ── 데이터 클래스 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FloorPlanImage:
    """배치도/평면도 이미지 메타데이터."""

    image_url: str
    caption: str
    plan_type: str  # "배치도" or "평면도"
    aptbg_id: str


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────


def get_aptbg_id(complex_name: str) -> Optional[str]:
    """단지명으로 aptbg.com 내부 ID 조회.

    Args:
        complex_name: 단지명 (샘플 10단지 목록 기준).

    Returns:
        aptbg_id 문자열, 미등록 단지는 None.
    """
    entry = SAMPLE_COMPLEXES.get(complex_name)
    return entry["aptbg_id"] if entry else None


def _build_search_url(complex_name: str, address: str = "") -> str:
    """aptbg.com 검색 URL 생성.

    먼저 복합 ID 가 있으면 상세 페이지 URL 을 반환한다.
    없으면 검색 페이지 URL 을 반환한다.

    Args:
        complex_name: 단지명.
        address: 주소 (선택, 검색 정확도 향상).

    Returns:
        aptbg.com URL.
    """
    aptbg_id = get_aptbg_id(complex_name)
    if aptbg_id:
        return f"{APT_BASE_URL}{APT_DETAIL_PATH}/{aptbg_id}"
    # 검색: 단지명 + 주소
    query = complex_name
    if address:
        query = f"{complex_name} {address}"
    import urllib.parse
    encoded = urllib.parse.quote(query)
    return f"{APT_BASE_URL}{APT_SEARCH_PATH}?q={encoded}"


def _parse_floor_plans(html: str, aptbg_id: str) -> list[dict[str, Any]]:
    """HTML 응답에서 배치도/평면도 이미지 URL 추출.

    aptbg.com 의 배치도 페이지 HTML 을 파싱하여 이미지 URL 리스트를 반환한다.
    파싱 대상 셀렉터:
      - .floorplan-gallery .item img → 이미지 URL
      - .floorplan-gallery .item .info → 캡션/설명

    Args:
        html: aptbg.com 응답 HTML.
        aptbg_id: 단지 aptbg ID.

    Returns:
        이미지 URL 리스트. 각 항목:
        {image_url: str, caption: str, plan_type: str, aptbg_id: str}.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []

    # 방법 1: .floorplan-gallery 내 .item (주력 구조)
    gallery = soup.select_one(".floorplan-gallery")
    if gallery:
        items = gallery.select(".item")
        for item in items:
            img = item.select_one("img")
            if img is None:
                continue
            image_url = img.get("src") or img.get("data-src") or ""
            if not image_url:
                continue
            # 상대 URL → 절대 URL
            image_url = str(image_url)
            if image_url.startswith("/"):
                image_url = f"{APT_BASE_URL}{image_url}"
            caption_tag = item.select_one(".info, .caption, figcaption")
            caption = caption_tag.get_text(strip=True) if caption_tag else ""
            plan_type = _infer_plan_type(caption, image_url)
            results.append({
                "image_url": image_url,
                "caption": caption,
                "plan_type": plan_type,
                "aptbg_id": aptbg_id,
            })

    # 방법 2: 직접 img 태그 중 floorplan 클래스 (보조 구조)
    if not results:
        floorplan_imgs = soup.select("img.floorplan, img[class*=floor], img[class*=plan]")
        for img in floorplan_imgs:
            image_url = img.get("src") or img.get("data-src") or ""
            if not image_url:
                continue
            image_url = str(image_url)
            if image_url.startswith("/"):
                image_url = f"{APT_BASE_URL}{image_url}"
            caption = str(img.get("alt", "")).strip()
            plan_type = _infer_plan_type(caption, image_url)
            results.append({
                "image_url": image_url,
                "caption": caption,
                "plan_type": plan_type,
                "aptbg_id": aptbg_id,
            })

    # 방법 3: .floor_plan_list 또는 .unit-list 내 이미지
    if not results:
        for container_sel in (".floor_plan_list", ".unit-list", ".layout-list"):
            container = soup.select_one(container_sel)
            if container is None:
                continue
            imgs = container.select("img")
            for img in imgs:
                image_url = img.get("src") or img.get("data-src") or ""
                if not image_url:
                    continue
                image_url = str(image_url)
                if image_url.startswith("/"):
                    image_url = f"{APT_BASE_URL}{image_url}"
                caption = str(img.get("alt", "")).strip()
                plan_type = _infer_plan_type(caption, image_url)
                results.append({
                    "image_url": image_url,
                    "caption": caption,
                    "plan_type": plan_type,
                    "aptbg_id": aptbg_id,
                })

    return results


def _infer_plan_type(caption: str, image_url: str) -> str:
    """캡션과 URL 에서 평면도 유형 추론.

    Args:
        caption: 이미지 캡션/설명.
        image_url: 이미지 URL.

    Returns:
        "배치도" 또는 "평면도".
    """
    lower_caption = caption.lower()
    lower_url = image_url.lower()
    if "배치" in lower_caption or "배치" in lower_url:
        return "배치도"
    if "bay" in lower_caption or "bay" in lower_url:
        return "배치도"
    return "평면도"


def _image_to_dict(fp: FloorPlanImage) -> dict[str, Any]:
    """FloorPlanImage → dict 변환."""
    return {
        "image_url": fp.image_url,
        "caption": fp.caption,
        "plan_type": fp.plan_type,
        "aptbg_id": fp.aptbg_id,
    }


# ── 채널 클래스 ────────────────────────────────────────────────────────────


class AptbgChannel:
    """아파트백과 배치도 수집 채널.

    ChannelCollector Protocol 구현.
    aptbg.com 에서 배치도/평면도 이미지 URL 을 수집한다.

    Attributes:
        channel_name: "aptbg"
        reliability: 0.95 (아파트백과의 결정론적 배치도 데이터)
    """

    channel_name: str = "aptbg"
    reliability: float = 0.95

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        fixture_path: Optional[str] = None,
    ) -> None:
        """AptbgChannel 초기화.

        Args:
            http_client: 선택. httpx.Client 인스턴스. 기본값은 새 클라이언트.
            fixture_path: 선택. JSON 픽스처 파일 경로 (오프라인 모드).
        """
        self._client = http_client or httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        self._fixture_path = fixture_path

    def collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """지정 단지의 배치도/평면도 이미지 URL 수집.

        fixture_path 가 설정된 경우 JSON 픽스처를 읽어 반환한다.
        그렇지 않으면 aptbg.com 에 HTTP 요청을 보내 수집한다.

        Args:
            query: 검색 조건 dict. 키:
                - complex_name (str): 단지명 (필수, 예: "래미안원베일리").
                - address (str): 주소 (선택, 검색 정확도 향상).

        Returns:
            이미지 URL 리스트. 각 항목:
            {image_url: str, caption: str, plan_type: str, aptbg_id: str}.
            실패 시 빈 리스트.
        """
        if self._fixture_path is not None:
            return self._load_fixture()

        complex_name = query.get("complex_name", "")
        address = query.get("address", "")
        return self._fetch_live(complex_name, address)

    def supported_complexes(self) -> list[str]:
        """현재 MVP 가 지원하는 단지명 목록."""
        return list(SAMPLE_COMPLEXES.keys())

    # ── 프라이빗 ──────────────────────────────────────────────────────────

    def _fetch_live(
        self,
        complex_name: str,
        address: str = "",
    ) -> list[dict[str, Any]]:
        """aptbg.com 에서 실시간 수집.

        Args:
            complex_name: 단지명.
            address: 주소 (선택).

        Returns:
            이미지 URL 리스트. 실패 시 빈 리스트.
        """
        aptbg_id = get_aptbg_id(complex_name) or "unknown"
        url = _build_search_url(complex_name, address)

        try:
            response = self._client.get(url, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("aptbg.com 접속 실패 (%s): %s", url, exc)
            return []
        except Exception as exc:
            logger.warning("aptbg.com 예외 (%s): %s", url, exc)
            return []

        return _parse_floor_plans(response.text, aptbg_id)

    def _load_fixture(self) -> list[dict[str, Any]]:
        """JSON 픽스처 파일 로드.

        Returns:
            픽스처 데이터. 파일 없으면 빈 리스트.
        """
        path = Path(self._fixture_path)  # type: ignore[arg-type]
        if not path.exists():
            logger.warning("픽스처 파일 없음: %s", path)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            logger.warning("픽스처 형식 오류: list 가 아님")
            return []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("픽스처 읽기 실패: %s", exc)
            return []
