"""
Core logic for discovering and downloading CAA-PL ArcGIS obstacle data.

Adapted from caa_pl_obstacle_explorer.py — uses QGIS network API when available,
falls back to urllib for standalone testing.
"""

import json
import ssl
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ── Configuration ─────────────────────────────────────────────────────────────
APP_ID = "252d2be2e6104adcb9be8201660a05b3"
PORTAL_BASE = "https://caa-pl.maps.arcgis.com"
SHARING_REST = f"{PORTAL_BASE}/sharing/rest"
TIMEOUT = 30


# ── SSL fallback ──────────────────────────────────────────────────────────────

def _get_ssl_context():
    try:
        ctx = ssl.create_default_context()
        import certifi  # noqa: F401
        return ctx
    except ImportError:
        pass
    return ssl._create_unverified_context()


_SSL_CTX = _get_ssl_context()


# ── Network helpers ───────────────────────────────────────────────────────────

def fetch_json(url, params=None, label=""):
    """Fetch JSON from a URL with error handling."""
    if params is None:
        params = {}
    params.setdefault("f", "json")

    full_url = f"{url}?{urlencode(params)}" if params else url
    try:
        req = Request(full_url, headers={"User-Agent": "CAA-PL-Explorer/1.0"})
        with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            return None
        return data
    except (HTTPError, URLError, json.JSONDecodeError):
        return None


# ── App / web map resolution ─────────────────────────────────────────────────

def get_app_item(app_id=APP_ID):
    url = f"{SHARING_REST}/content/items/{app_id}"
    return fetch_json(url, label="app item")


def get_app_data(app_id=APP_ID):
    url = f"{SHARING_REST}/content/items/{app_id}/data"
    return fetch_json(url, label="app config")


def get_webmap_data(webmap_id):
    url = f"{SHARING_REST}/content/items/{webmap_id}/data"
    return fetch_json(url, label="web map data")


# ── Layer inspection ─────────────────────────────────────────────────────────

def get_layer_info(layer_url):
    return fetch_json(layer_url, label=layer_url)


def get_layer_count(layer_url):
    params = {"where": "1=1", "returnCountOnly": "true"}
    return fetch_json(f"{layer_url}/query", params=params, label=f"{layer_url} count")


# ── Discovery pipeline ───────────────────────────────────────────────────────

def discover_layers(app_id=APP_ID, progress_callback=None):
    """
    Discover all layers from the CAA-PL ArcGIS app.

    Returns a list of dicts: [{url, title, layer_type, visibility, sublayers}, ...]
    progress_callback(message) is called with status updates.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    _progress("Pobieranie konfiguracji aplikacji / Fetching app configuration...")
    app_data = get_app_data(app_id)
    if not app_data:
        _progress("Nie udalo sie pobrac konfiguracji / Could not fetch app config")
        return []

    map_config = app_data.get("map", {})
    webmap_id = map_config.get("itemId")

    # Collect service URLs from widget configs
    service_urls_from_config = []
    for widget_key in ("widgetPool", "widgetOnScreen"):
        widgets = app_data.get(widget_key, {}).get("widgets", [])
        for w in widgets:
            w_config = w.get("config", {})
            if isinstance(w_config, dict):
                for key in ("layerInfosToShow", "layers", "featureLayers", "dataSource"):
                    val = w_config.get(key)
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict) and "url" in item:
                                service_urls_from_config.append(item["url"])

    # Resolve web map layers
    operational_layers = []
    if webmap_id:
        _progress(f"Pobieranie warstw mapy / Fetching web map layers ({webmap_id})...")
        wm_data = get_webmap_data(webmap_id)
        if wm_data:
            operational_layers = wm_data.get("operationalLayers", [])

    # Build layer URL list
    layer_entries = []
    seen_urls = set()

    for layer in operational_layers:
        url = layer.get("url", "")
        title = layer.get("title", layer.get("name", ""))
        layer_type = layer.get("layerType", "")
        visibility = layer.get("visibility", True)

        if url and url not in seen_urls:
            seen_urls.add(url)
            sublayers = layer.get("layers", [])
            entry = {
                "url": url,
                "title": title,
                "layer_type": layer_type,
                "visibility": visibility,
                "sublayers": [
                    {"id": sl.get("id"), "name": sl.get("name", sl.get("title", ""))}
                    for sl in sublayers
                ],
            }
            layer_entries.append(entry)

            # Add sublayers as separate entries
            for sl in sublayers:
                sl_id = sl.get("id")
                if sl_id is not None:
                    sl_url = f"{url}/{sl_id}"
                    if sl_url not in seen_urls:
                        seen_urls.add(sl_url)
                        layer_entries.append({
                            "url": sl_url,
                            "title": sl.get("name", sl.get("title", f"Sublayer {sl_id}")),
                            "layer_type": layer_type,
                            "visibility": visibility,
                            "sublayers": [],
                        })

    for url in service_urls_from_config:
        if url not in seen_urls:
            seen_urls.add(url)
            layer_entries.append({
                "url": url,
                "title": "",
                "layer_type": "",
                "visibility": True,
                "sublayers": [],
            })

    _progress(f"Znaleziono {len(layer_entries)} warstw / Found {len(layer_entries)} layers")
    return layer_entries


def inspect_layer(layer_url, progress_callback=None):
    """
    Inspect a single layer, returning metadata dict or None.
    """
    info = get_layer_info(layer_url)
    if not info:
        return None

    count_data = get_layer_count(layer_url)
    count = count_data.get("count", "?") if count_data else "?"

    fields = info.get("fields", [])
    capabilities = info.get("capabilities", "")

    return {
        "url": layer_url,
        "name": info.get("name", "Unknown"),
        "type": info.get("type", "Unknown"),
        "geometryType": info.get("geometryType", "N/A"),
        "featureCount": count,
        "capabilities": capabilities,
        "fields": fields,
        "maxRecordCount": info.get("maxRecordCount", 1000),
        "queryable": "Query" in capabilities,
    }


# ── Feature download ─────────────────────────────────────────────────────────

def download_features(layer_url, bbox=None, max_features=None, progress_callback=None):
    """
    Download features from a layer. Returns list of Esri JSON features.
    bbox: (xmin, ymin, xmax, ymax) in WGS84, or None.
    """
    all_features = []
    offset = 0
    batch_size = 1000

    geometry = ""
    geometry_type = ""

    if bbox:
        xmin, ymin, xmax, ymax = bbox
        geometry = json.dumps({
            "xmin": xmin, "ymin": ymin,
            "xmax": xmax, "ymax": ymax,
            "spatialReference": {"wkid": 4326}
        })
        geometry_type = "esriGeometryEnvelope"

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "returnGeometry": "true",
        }
        if geometry:
            params["geometry"] = geometry
            params["geometryType"] = geometry_type
            params["inSR"] = 4326
            params["spatialRel"] = "esriSpatialRelIntersects"

        if progress_callback:
            progress_callback(f"Pobieranie obiektow / Fetching features (offset={offset})...")

        data = fetch_json(f"{layer_url}/query", params=params, label=f"query offset={offset}")
        if not data or "features" not in data:
            break

        features = data["features"]
        if not features:
            break

        all_features.extend(features)

        if max_features and len(all_features) >= max_features:
            all_features = all_features[:max_features]
            break

        exceeded = data.get("exceededTransferLimit", False)
        if not exceeded and len(features) < batch_size:
            break

        offset += len(features)

    return all_features


def esri_features_to_geojson(features):
    """Convert Esri JSON features to a GeoJSON FeatureCollection dict."""
    geojson_features = []

    for feat in features:
        geom = feat.get("geometry", {})
        attrs = feat.get("attributes", {})

        gj_geom = None
        if "x" in geom and "y" in geom:
            coords = [geom["x"], geom["y"]]
            if "z" in geom:
                coords.append(geom["z"])
            gj_geom = {"type": "Point", "coordinates": coords}
        elif "rings" in geom:
            if len(geom["rings"]) == 1:
                gj_geom = {"type": "Polygon", "coordinates": geom["rings"]}
            else:
                gj_geom = {"type": "MultiPolygon", "coordinates": [[r] for r in geom["rings"]]}
        elif "paths" in geom:
            if len(geom["paths"]) == 1:
                gj_geom = {"type": "LineString", "coordinates": geom["paths"][0]}
            else:
                gj_geom = {"type": "MultiLineString", "coordinates": geom["paths"]}
        elif "points" in geom:
            gj_geom = {"type": "MultiPoint", "coordinates": geom["points"]}

        geojson_features.append({
            "type": "Feature",
            "geometry": gj_geom,
            "properties": attrs,
        })

    return {
        "type": "FeatureCollection",
        "features": geojson_features,
    }
