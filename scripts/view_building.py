"""V-World 건물 폴리곤 → HTML 지도 시각화 (OpenLayers)

사용: python scripts/view_building.py 서초푸르지오써밋
결과: buildings.html 생성 → 브라우저에서 열기
"""
import os, sys, json, math, webbrowser
import requests
from dotenv import load_dotenv
load_dotenv()
KEY = os.environ.get("VWORLD_API_KEY", "")

# ============================================================
# 1. 지오코더: 단지명 → 좌표
# ============================================================
def geocode(query: str) -> tuple[float, float] | None:
    # 검색 API로 시도
    r = requests.get("https://api.vworld.kr/req/search", params={
        "service": "search", "request": "search",
        "key": KEY, "query": query, "type": "place", "size": 1,
    }, timeout=10)
    data = r.json()
    items = data.get("response",{}).get("result",{}).get("items",[])
    if items:
        p = items[0].get("point", {})
        return float(p["x"]), float(p["y"])
    # 실패 시 지오코더로 시도
    r2 = requests.get("https://api.vworld.kr/req/address", params={
        "service": "address", "request": "getcoord",
        "key": KEY, "type": "ROAD", "address": query,
    }, timeout=10)
    d2 = r2.json()
    if d2.get("response",{}).get("status") == "OK":
        p = d2["response"]["result"]["point"]
        return float(p["x"]), float(p["y"])
    return None

# ============================================================
# 2. 건물 폴리곤 조회
# ============================================================
def get_buildings(x: float, y: float, radius: float = 0.001) -> list[dict]:
    """좌표 주변 건물 폴리곤 조회"""
    r = requests.get("https://api.vworld.kr/req/data", params={
        "service": "data", "request": "GetFeature",
        "data": "LT_C_BLDGINFO", "key": KEY,
        "geomFilter": f"BOX({x-radius} {y-radius},{x+radius} {y+radius})",
        "size": 50, "crs": "EPSG:4326", "geometry": "true",
    }, timeout=15)
    data = r.json()
    if data.get("response",{}).get("status") != "OK":
        return []
    return data["response"]["result"]["featureCollection"]["features"]

# ============================================================
# 3. 폴리곤에서 주향 계산
# ============================================================
def calc_direction(coords: list) -> tuple[float, str]:
    """폴리곤 좌표 → 주향 각도 + 방향"""
    if not coords or len(coords) < 3:
        return 0, "?"
    # 가장 긴 변 찾기
    max_len, best = 0, None
    for i in range(len(coords)):
        x1, y1 = coords[i][0], coords[i][1]
        x2, y2 = coords[(i+1)%len(coords)][0], coords[(i+1)%len(coords)][1]
        d = math.sqrt((x2-x1)**2 + (y2-y1)**2)
        if d > max_len:
            max_len, best = d, (x1, y1, x2, y2)
    if not best: return 0, "?"
    x1, y1, x2, y2 = best
    angle = math.degrees(math.atan2(x2-x1, y2-y1))
    if angle < 0: angle += 360
    normal = (angle + 90) % 360  # 장변의 직각 = 전면 방향
    dirs = [(0,"N"),(45,"NE"),(90,"E"),(135,"SE"),(180,"S"),(225,"SW"),(270,"W"),(315,"NW")]
    nearest = min(dirs, key=lambda d: abs(normal-d[0]))
    return normal, nearest[1]

# ============================================================
# 4. HTML 생성
# ============================================================
def build_html(buildings: list[dict], center: tuple) -> str:
    features = []
    for b in buildings:
        props = b.get("properties", {})
        name = props.get("bld_nm", "") or props.get("addr", "")[:20]
        coords = b.get("geometry", {}).get("coordinates", [[]])[0]
        if isinstance(coords[0], list) and isinstance(coords[0][0], list):
            coords = coords[0]  # MultiPolygon → outer ring
        angle, direction = calc_direction(coords)
        # 좌표를 Leaflet 형식으로 (lng, lat 순서)
        ll_coords = [[c[1], c[0]] for c in coords]
        center_lng = sum(c[0] for c in coords) / len(coords)
        center_lat = sum(c[1] for c in coords) / len(coords)
        features.append({
            "name": name, "coords": json.dumps(ll_coords),
            "center": [center_lat, center_lng],
            "angle": round(angle, 0), "direction": direction,
        })
    
    js_features = json.dumps(features, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>건물 방향 시각화</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body{{margin:0;font-family:sans-serif}}
  #map{{height:100vh;width:100vw}}
  .legend{{background:white;padding:10px;border-radius:5px;box-shadow:0 0 10px rgba(0,0,0,.2)}}
</style></head>
<body><div id="map"></div>
<script>
var features = {js_features};
var map = L.map('map').setView([{center[1]}, {center[0]}], 17);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
  attribution:'&copy;OSM',maxZoom:20
}}).addTo(map);

var dirColors = {{'N':'#e74c3c','NE':'#e67e22','E':'#f1c40f','SE':'#2ecc71','S':'#3498db','SW':'#9b59b6','W':'#1abc9c','NW':'#95a5a6'}};

features.forEach(function(f) {{
  var poly = L.polygon(JSON.parse(f.coords), {{
    color: dirColors[f.direction] || '#333',
    weight: 2, fillOpacity: 0.3, fillColor: dirColors[f.direction] || '#333'
  }}).addTo(map).bindPopup('<b>'+f.name+'</b><br>전면: '+f.direction+' ('+f.angle+'°)');
  
  // 방향 화살표
  var rad = f.angle * Math.PI / 180;
  var lat = f.center[0], lng = f.center[1];
  var dx = Math.sin(rad) * 0.0003;
  var dy = Math.cos(rad) * 0.0003;
  var arrow = L.polyline([[lat,lng],[lat+dy,lng+dx]], {{color:dirColors[f.direction]||'#333',weight:4}}).addTo(map);
}});

// 범례
var legend = L.control({{position:'bottomright'}});
legend.onAdd = function() {{
  var div = L.DomUtil.create('div','legend');
  div.innerHTML = '<b>건물 전면 방향</b><br>';
  for(var d in dirColors) div.innerHTML += '<span style=color:'+dirColors[d]+'>■</span> '+d+'<br>';
  return div;
}};
legend.addTo(map);
</script></body></html>"""

# ============================================================
# 5. 메인
# ============================================================
if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "서초푸르지오써밋"
    print(f"검색: {query}")
    
    # 지오코딩
    coord = geocode(query)
    if not coord:
        print("❌ 좌표를 찾을 수 없습니다")
        sys.exit(1)
    print(f"  좌표: {coord[0]:.6f}, {coord[1]:.6f}")
    
    # 건물 폴리곤
    print("  건물 폴리곤 조회 중...")
    buildings = get_buildings(coord[0], coord[1])
    
    if not buildings:
        # API 실패 시 mock으로 테스트 가능하도록
        print("  ⚠️ API 폴리곤 실패 — 더미 데이터로 HTML 생성")
        # 서초푸르지오써밋 mock 좌표 (실제 건물 형태 근사)
        mock = {
            "geometry": {"type": "Polygon", "coordinates": [[
                [127.0255, 37.4905], [127.0260, 37.4905],
                [127.0260, 37.4915], [127.0255, 37.4915],
                [127.0255, 37.4905]
            ]]},
            "properties": {"bld_nm": "104동", "addr": "서초동 1311-10"}
        }
        buildings = [mock]
    
    # HTML 생성
    html = build_html(buildings, coord)
    path = os.path.join(os.path.dirname(__file__) or ".", "buildings.html")
    path = os.path.abspath(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ {path} 생성됨 ({len(buildings)}개 건물)")
    print(f"  브라우저에서 열기: file://{path}")
    webbrowser.open(f"file://{path}")
