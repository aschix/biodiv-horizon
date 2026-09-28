"""Copernicus Data Space Ecosystem (CDSE) & EEA DiscoMap — Daten-Ingestion.

Dieses Modul stellt die Kernmethoden für den Download und die Verarbeitung
von Copernicus Land Monitoring Service (CLMS) Rasterdaten bereit:

Sprint 2a (Direkte HTTP- & REST-Pipelines):
- EEA DiscoMap ArcGIS ImageServer exportImage (IMD, WAW, FTY)
- CDSE STAC Suche (direkt via HTTP oder pystac-client)
- CDSE OAuth 2.0 Keycloak Authentifizierung & OData ZIP-Download
- Fensterbasiertes Raster-Clipping mit rasterio & pyproj
- Detaillierte GeoTIFF Metadaten-Inspektion

Sprint 2b (High-Level COG Streaming):
- Cloud Optimized GeoTIFF (COG) Streaming via rioxarray & GDAL VSICURL
- Einheitliche Reprojektion und Export
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds as window_from_bounds
from pyproj import Transformer
import requests

try:
    import rioxarray  # noqa: F401  — registriert .rio accessor
    import xarray as xr
except (ImportError, OSError):
    rioxarray = None
    xr = None

from pystac_client import Client
from pystac_client.exceptions import APIError

from biodiv_horizon.config import (
    CDSE_PASSWORD,
    CDSE_STAC_URL,
    CDSE_USERNAME,
    CLMS_LAYERS,
    CLMS_LAYERS_BY_CODE,
    COPERNICUS_DIR,
    CRS_AUSTRIA,
    DOWNLOAD_BBOX,
    get_clms_layer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. STAC-Katalog erkunden (pystac-client & einfaches REST)
# ---------------------------------------------------------------------------

def open_cdse_catalog() -> Client:
    """Öffnet den CDSE STAC-Katalog via pystac-client (kein Login für Metadaten nötig)."""
    try:
        catalog = Client.open(CDSE_STAC_URL)
        logger.info("CDSE STAC-Katalog verbunden: %s", catalog.title)
        return catalog
    except APIError as e:
        raise ConnectionError(f"Kann CDSE STAC nicht erreichen: {e}") from e


def list_collections(catalog: Client) -> list[str]:
    """Listet alle verfügbaren Collections im CDSE-Katalog."""
    collections = list(catalog.get_collections())
    names = [c.id for c in collections]
    logger.info("Verfügbare Collections (%d): %s", len(names), names[:10])
    return names


# Standard CLMS-Collections für STAC, direkt abgeleitet aus CLMS_LAYERS
DEFAULT_CLMS_COLLECTIONS: list[str] = [
    layer["stac_collection"]
    for layer in CLMS_LAYERS.values()
    if layer.get("stac_collection")
]


def search_clms_items(
    catalog: Client,
    bbox: list[float] | None = None,
    datetime_range: str = "2021-01-01/2024-12-31",
    collections: list[str] | None = None,
    max_items: int = 50,
) -> list:
    """Sucht CLMS-Items im STAC-Katalog via pystac-client für das angegebene Gebiet.

    Args:
        catalog: Geöffneter CDSE STAC-Client
        bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
        datetime_range: ISO8601 Zeitraum, z.B. '2021-01-01/2024-12-31'
        collections: Liste der STAC-Collection-IDs (Standard: DEFAULT_CLMS_COLLECTIONS)
        max_items: Maximale Anzahl zurückgegebener Items pro Collection

    Returns:
        Liste der gefundenen STAC-Items (pystac.Item)
    """
    bbox = bbox or DOWNLOAD_BBOX
    collection_ids = collections or DEFAULT_CLMS_COLLECTIONS

    all_items = []
    for collection_id in collection_ids:
        for attempt in range(3):
            try:
                search = catalog.search(
                    collections=[collection_id],
                    bbox=bbox,
                    datetime=datetime_range,
                    max_items=max_items,
                )
                items = list(search.items())
                logger.info("Collection '%s': %d Items gefunden", collection_id, len(items))
                all_items.extend(items)
                time.sleep(0.5)  # Schont das CDSE WAF Rate-Limit
                break
            except APIError as e:
                if "429" in str(e) or "Rate limit" in str(e):
                    wait_sec = 1.5 * (attempt + 1)
                    logger.warning(
                        "CDSE Rate-Limit bei Collection '%s', warte %.1fs (Versuch %d/3)...",
                        collection_id,
                        wait_sec,
                        attempt + 1,
                    )
                    time.sleep(wait_sec)
                    continue
                logger.warning("Collection '%s' nicht verfügbar oder Fehler: %s", collection_id, e)
                break

    return all_items


def search_stac_items_simple(
    collection: str,
    bbox: list[float],
    limit: int = 5,
) -> list[dict]:
    """Durchsucht den CDSE-STAC-Katalog über einfache HTTP-Requests (ohne pystac-client).

    Args:
        collection: STAC Collection ID
        bbox: [minLon, minLat, maxLon, maxLat] in WGS84
        limit: Maximale Anzahl Items

    Returns:
        Liste von GeoJSON-Feature-Dictionaries
    """
    url = f"{CDSE_STAC_URL}/collections/{collection}/items"
    params = {
        "bbox": ",".join(str(v) for v in bbox),
        "limit": limit,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    features = response.json().get("features", [])
    logger.info("STAC Simple Suche '%s': %d Items", collection, len(features))
    return features


def print_item_summary(items: list) -> None:
    """Gibt eine übersichtliche Tabelle der gefundenen STAC-Items aus."""
    if not items:
        print("Keine Items gefunden.")
        return

    print(f"\n{'ID':<50} {'Datum':<12} {'Assets':<30}")
    print("-" * 95)
    for item in items:
        # Funktioniert für pystac.Item sowie dict
        if hasattr(item, "datetime"):
            date = item.datetime.strftime("%Y-%m-%d") if item.datetime else "N/A"
            item_id = item.id
            assets = ", ".join(list(item.assets.keys())[:5])
        else:
            props = item.get("properties", {})
            date = props.get("datetime", "N/A")[:10]
            item_id = item.get("id", "N/A")
            assets = ", ".join(list(item.get("assets", {}).keys())[:5])
        print(f"{item_id[:48]:<50} {date:<12} {assets:<30}")


# ---------------------------------------------------------------------------
# 2. EEA DiscoMap ArcGIS ImageServer exportImage (Sprint 2a)
# ---------------------------------------------------------------------------

def download_eea_layer(
    service_name: str,
    output_path: Path,
    bbox: list[float],
    img_w: int = 844,
    img_h: int = 388,
    bbox_sr: int = 4326,
    resolution_m: int | None = None,
) -> Path:
    """Lädt einen EEA DiscoMap ImageServer-Layer als GeoTIFF herunter.

    Nutzt den ArcGIS-nativen exportImage-Endpunkt.
    Der Server schneidet serverseitig zu und liefert einen binären GeoTIFF-Strom.

    Args:
        service_name: ArcGIS-Servicename (z.B. 'HRL_ImperviousnessDensity_2018')
        output_path:  Zielpfad für das GeoTIFF
        bbox:         [minLon, minLat, maxLon, maxLat] in WGS84
        img_w, img_h: Ausgabe-Pixelgröße (wird ignoriert, falls resolution_m gesetzt ist)
        bbox_sr:      Spatial Reference als EPSG-Code (Standard: 4326)
        resolution_m: Optionale Zielauflösung in Metern (z.B. 40 für Schnelltest, 10 für volle Auflösung)

    Returns:
        Pfad zur gespeicherten GeoTIFF-Datei
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if resolution_m is not None and resolution_m > 0:
        # Breiten- und Längengrade in Meter approximieren für Donau-Auen (~48°N)
        lon_m = (bbox[2] - bbox[0]) * 111320 * 0.67
        lat_m = (bbox[3] - bbox[1]) * 111320
        img_w = max(1, int(lon_m / resolution_m))
        img_h = max(1, int(lat_m / resolution_m))

    base_url = "https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic"
    export_url = f"{base_url}/{service_name}/ImageServer/exportImage"

    params = {
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "bboxSR": str(bbox_sr),
        "size": f"{img_w},{img_h}",
        "format": "tiff",
        "f": "image",
        "pixelType": "U8",
        "noDataInterpretation": "esriNoDataMatchAny",
    }

    logger.info("EEA REST Export '%s': size=%dx%d px (bbox=%s)", service_name, img_w, img_h, bbox)
    t0 = time.time()
    response = requests.get(export_url, params=params, timeout=120)
    response.raise_for_status()
    elapsed = time.time() - t0

    content_type = response.headers.get("Content-Type", "")
    if "json" in content_type or ("tiff" not in content_type and "image" not in content_type):
        try:
            error_info = response.json()
        except Exception:
            error_info = response.text[:200]
        raise RuntimeError(f"EEA DiscoMap Fehler ({service_name}): {error_info}")

    output_path.write_bytes(response.content)
    size_kb = len(response.content) / 1024
    logger.info("✅ EEA REST Download: %s (%.1f KB in %.1fs)", output_path.name, size_kb, elapsed)
    return output_path


def download_clms_via_wcs(
    layer: str,
    bbox: list[float],
    output_path: Path,
    resolution_m: int = 100,
) -> Path:
    """Kompatibilitäts-Wrapper für download_eea_layer.

    Auf dem EEA-Server ist OGC-WCS deaktiviert, daher wird transparent der
    native exportImage-Endpunkt genutzt.
    """
    service_aliases = {
        "IMD": "HRL_ImperviousnessDensity_2018",
        "IMD_2018": "HRL_ImperviousnessDensity_2018",
        "TCD": "HRL_TreeCoverDensity_2018",
        "TCD_2018": "HRL_TreeCoverDensity_2018",
        "GRA": "HRL_Grassland_2018",
        "GRA_2018": "HRL_Grassland_2018",
        "FTY": "HRL_ForestType_2018",
        "FTY_2018": "HRL_ForestType_2018",
        "WAW": "HRL_WaterWetness_2018",
        "WAW_2018": "HRL_WaterWetness_2018",
    }
    service_name = service_aliases.get(layer, layer)
    return download_eea_layer(
        service_name=service_name,
        output_path=output_path,
        bbox=bbox,
        resolution_m=resolution_m,
    )


# ---------------------------------------------------------------------------
# 3. CDSE Authentifizierung & OData Download (Sprint 2a)
# ---------------------------------------------------------------------------

def get_cdse_token(
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Holt einen OAuth 2.0 Bearer-Token vom CDSE Identity Provider (Keycloak).

    Nutzt den Resource Owner Password Credentials Grant (ROPC) Flow.
    Token-Lebensdauer: ca. 10 Minuten.

    Args:
        username: CDSE-Benutzername (E-Mail). Falls None, wird CDSE_USERNAME aus config/.env genutzt.
        password: CDSE-Passwort. Falls None, wird CDSE_PASSWORD aus config/.env genutzt.

    Returns:
        access_token (JWT-String)
    """
    user = username or CDSE_USERNAME
    pwd = password or CDSE_PASSWORD

    if not user or not pwd:
        raise ValueError(
            "CDSE Credentials fehlen! Bitte CDSE_USERNAME und CDSE_PASSWORD "
            "in der .env-Datei setzen oder als Parameter übergeben."
        )

    url = (
        "https://identity.dataspace.copernicus.eu"
        "/auth/realms/CDSE/protocol/openid-connect/token"
    )
    payload = {
        "client_id": "cdse-public",
        "username": user,
        "password": pwd,
        "grant_type": "password",
    }

    logger.info("Token-Request an CDSE Identity Provider (%s)...", user)
    response = requests.post(url, data=payload, timeout=20)
    if response.status_code != 200:
        err = response.json().get("error_description", response.text[:200]) if "json" in response.headers.get("content-type", "") else response.text[:200]
        raise RuntimeError(f"CDSE Authentication fehlgeschlagen (HTTP {response.status_code}): {err}")

    token = response.json()["access_token"]
    logger.info("✅ CDSE Bearer-Token erhalten (Länge: %d Zeichen)", len(token))
    return token


def download_cdse_product(
    product_url: str,
    output_path: Path,
    token: str | None = None,
    chunk_size: int = 1024 * 1024,
) -> Path:
    """Lädt ein CDSE OData-Produkt (ZIP-Archiv) via HTTPS herunter (streaming).

    Args:
        product_url: OData-URL (z.B. https://download.dataspace.copernicus.eu/odata/v1/Products(...)/$value)
        output_path: Zielpfad für das ZIP-Archiv
        token: Gültiger CDSE Bearer-Token (wird automatisch geholt falls None)
        chunk_size: Streaming-Chunkgröße in Bytes (Standard: 1 MB)

    Returns:
        Pfad zur gespeicherten ZIP-Datei
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not product_url.endswith("/$value"):
        product_url = f"{product_url}/$value"

    auth_token = token or get_cdse_token()
    headers = {"Authorization": f"Bearer {auth_token}"}

    logger.info("Download CDSE Product: %s → %s", product_url[:80], output_path.name)
    with requests.get(product_url, headers=headers, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info("✅ CDSE Produkt gespeichert: %s (%.1f MB)", output_path.name, size_mb)
    return output_path


# ---------------------------------------------------------------------------
# 4. Raster-Manipulation & Metadaten-Inspektion (Sprint 2a)
# ---------------------------------------------------------------------------

def clip_raster_to_bbox(
    input_path: Path,
    output_path: Path,
    bbox: list[float],
    bbox_crs: str = "EPSG:4326",
) -> Path:
    """Schneidet ein GeoTIFF auf eine BBox zu (fensterbasiert via rasterio).

    Transformiert die BBox automatisch vom Eingabe-CRS in das Raster-CRS.
    Das Raster wird verlustfrei und ohne Resampling ausgeschnitten und als
    getiltes GeoTIFF gespeichert.

    Args:
        input_path: Quell-GeoTIFF
        output_path: Ziel-GeoTIFF
        bbox: [minLon, minLat, maxLon, maxLat]
        bbox_crs: CRS der Bounding Box (Standard: EPSG:4326)

    Returns:
        Pfad zum zugeschnittenen GeoTIFF
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(input_path) as src:
        raster_crs_str = src.crs.to_string()

        transformer = Transformer.from_crs(bbox_crs, raster_crs_str, always_xy=True)
        minx, miny = transformer.transform(bbox[0], bbox[1])
        maxx, maxy = transformer.transform(bbox[2], bbox[3])

        window = window_from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        data = src.read(window=window)
        profile = src.profile.copy()
        profile.update({
            "height": data.shape[1],
            "width": data.shape[2],
            "transform": src.window_transform(window),
            "compress": "DEFLATE",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
        })
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data)

    size_kb = output_path.stat().st_size / 1024
    logger.info("✅ Raster geclippt: %s (%.1f KB)", output_path.name, size_kb)
    return output_path


def inspect_raster(path: Path, name: str = "") -> dict:
    """Liest Metadaten und Band-1-Statistik eines GeoTIFF mit rasterio aus.

    Gibt ein Dictionary mit CRS, Bounds, Shape, Dtype, NoData und deskriptiver
    Statistik (min, max, mean) zurück.
    """
    path = Path(path)
    display_name = name or path.name

    with rasterio.open(path) as src:
        data = src.read(1).astype(float)
        nd = src.nodata
        if nd is not None:
            data_valid = data[data != nd]
        else:
            data_valid = data.flatten()

        info = {
            "name": display_name,
            "path": path,
            "crs": str(src.crs),
            "bounds": src.bounds,
            "shape": (src.height, src.width),
            "pixel_unit": abs(src.transform.a),
            "dtype": str(src.dtypes[0]),
            "nodata": nd,
            "transform": src.transform,
            "min": float(data_valid.min()) if len(data_valid) > 0 else None,
            "max": float(data_valid.max()) if len(data_valid) > 0 else None,
            "mean": float(data_valid.mean()) if len(data_valid) > 0 else None,
        }
    return info


# ---------------------------------------------------------------------------
# 5. COG-Streaming & High-Level Ingestion (Sprint 2b)
# ---------------------------------------------------------------------------

def download_and_clip_raster(
    href: str,
    bbox: list[float],
    output_path: Path,
    target_crs: str = CRS_AUSTRIA,
) -> Path:
    """Lädt ein Raster (COG oder GeoTIFF) via rioxarray herunter und clippt es.

    Unterstützt HTTP Range Requests für Cloud Optimized GeoTIFFs (COGs).

    Args:
        href: URL oder lokaler Pfad zur Quell-Datei
        bbox: Ziel-BBox [min_lon, min_lat, max_lon, max_lat] in WGS84
        output_path: Ausgabepfad für die geclippte COG-Datei
        target_crs: Ziel-CRS für Reprojektion (Standard: Austrian Lambert)

    Returns:
        Pfad zur gespeicherten Datei
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Lade Raster via rioxarray: %s", href)
    logger.info("Clip auf BBox: %s → Ziel-CRS: %s", bbox, target_crs)

    global rioxarray, xr
    if xr is None or rioxarray is None:
        import rioxarray as _rxr  # noqa: F401
        import xarray as _xr

        rioxarray = _rxr
        xr = _xr

    ds: xr.DataArray = rioxarray.open_rasterio(
        href,
        chunks={"x": 2048, "y": 2048},
        lock=False,
    )

    ds_clipped = ds.rio.clip_box(
        minx=bbox[0],
        miny=bbox[1],
        maxx=bbox[2],
        maxy=bbox[3],
        crs="EPSG:4326",
    )

    if target_crs and ds_clipped.rio.crs and str(ds_clipped.rio.crs) != target_crs:
        ds_clipped = ds_clipped.rio.reproject(target_crs)

    ds_clipped.rio.to_raster(
        str(output_path),
        driver="COG",
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info("✅ COG Gespeichert: %s (%.1f MB)", output_path, size_mb)
    return output_path


def download_all_clms_layers(
    stac_items: list | None = None,
    bbox: list[float] | None = None,
    output_dir: Path | None = None,
    resolution_m: int | None = None,
    force: bool = False,
) -> dict[str, Path]:
    """Lädt alle CLMS-Layer für das Testgebiet herunter.

    Berücksichtigt die in CLMS_LAYERS definierte Quelle:
    - 'eea_rest': Direkter Download via ArcGIS ImageServer exportImage (EEA DiscoMap)
    - 'cdse_stac': STAC-Item Asset Download / COG-Streaming

    Args:
        stac_items: Gefundene STAC-Items (optional)
        bbox: Clip-BBox in WGS84
        output_dir: Ausgabeverzeichnis (Standard: COPERNICUS_DIR)
        resolution_m: Optionale Auflösung in Metern für EEA-Layer
        force: Falls True, werden bestehende Dateien überschrieben

    Returns:
        Dict layer_key → lokaler Dateipfad
    """
    bbox = bbox or DOWNLOAD_BBOX
    output_dir = output_dir or COPERNICUS_DIR
    stac_items = stac_items or []

    downloaded: dict[str, Path] = {}

    for layer_key, layer_info in CLMS_LAYERS.items():
        output_path = output_dir / layer_info["filename"]

        if output_path.exists() and not force:
            logger.info("Layer '%s' bereits vorhanden: %s", layer_key, output_path)
            downloaded[layer_key] = output_path
            continue

        source = layer_info.get("source", "")

        # 1. EEA REST Download (z.B. IMD, WAW, FTY)
        if source == "eea_rest" or layer_info.get("eea_service"):
            service_name = layer_info.get("eea_service") or layer_info.get("wcs_layer")
            if service_name:
                try:
                    logger.info("Lade Layer '%s' via EEA REST (%s)...", layer_key, service_name)
                    downloaded[layer_key] = download_eea_layer(
                        service_name=service_name,
                        output_path=output_path,
                        bbox=bbox,
                        resolution_m=resolution_m,
                    )
                    continue
                except Exception as e:
                    logger.warning("Download via EEA REST fehlgeschlagen für '%s': %s", layer_key, e)

        # 2. CDSE STAC Download (z.B. TCD, GRA)
        if source in ("cdse_stac", "stac") or layer_info.get("stac_collection"):
            matching_item = _find_matching_item(stac_items, layer_key)
            if matching_item is not None:
                asset_href = _get_asset_href(matching_item)
                if asset_href:
                    try:
                        downloaded[layer_key] = download_and_clip_raster(
                            href=asset_href,
                            bbox=bbox,
                            output_path=output_path,
                        )
                        continue
                    except Exception as e:
                        logger.warning("Download via STAC fehlgeschlagen für '%s': %s", layer_key, e)

        logger.warning("Keine Datenquelle für Layer '%s' verfügbar oder Download fehlgeschlagen", layer_key)

    return downloaded


def _find_matching_item(items: list, layer_key: str):
    """Findet das STAC-Item, das einem CLMS-Layer entspricht."""
    layer_info = CLMS_LAYERS.get(layer_key) or CLMS_LAYERS_BY_CODE.get(layer_key, {})
    target_collection = layer_info.get("stac_collection")

    # 1. Direkter Abgleich über stac_collection
    if target_collection:
        for item in items:
            col_id = getattr(item, "collection_id", None) or (item.get("collection") if isinstance(item, dict) else None)
            if col_id == target_collection:
                return item

    # 2. Fallback: Keyword-Matching
    short_code = layer_info.get("short_code", "")
    keywords = [layer_key, short_code] if short_code else [layer_key]

    for item in items:
        if hasattr(item, "id"):
            title = (item.properties.get("title", "") or "") + " " + item.id
        else:
            title = (item.get("properties", {}).get("title", "") or "") + " " + item.get("id", "")
        if any(kw.lower() in title.lower() for kw in keywords if kw):
            return item
    return None


def _get_asset_href(item) -> str | None:
    """Extrahiert die Download-URL aus einem STAC-Item (pystac.Item oder dict)."""
    preferred_keys = ["data", "download", "asset", "visual"]
    assets = item.assets if hasattr(item, "assets") else item.get("assets", {})

    for key in preferred_keys:
        if key in assets:
            val = assets[key]
            return val.href if hasattr(val, "href") else val.get("href")

    if assets:
        first = next(iter(assets.values()))
        return first.href if hasattr(first, "href") else first.get("href")
    return None
