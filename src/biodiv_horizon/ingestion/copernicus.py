"""Copernicus Data Space Ecosystem (CDSE) — STAC-basierte Daten-Ingestion.

Workflow:
1. STAC-Katalog auf CDSE durchsuchen (pystac-client)
2. CLMS-Produkte für Testgebiet und Zeitraum finden
3. Layer herunterladen, auf Bounding Box zuschneiden
4. Als Cloud Optimized GeoTIFF (COG) lokal speichern

Wichtige CDSE-Ressourcen:
- STAC-Browser: https://browser.dataspace.copernicus.eu/
- API-Doku:     https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- CLMS Produkte:https://land.copernicus.eu/en/products
"""

from __future__ import annotations

import logging
from pathlib import Path

import time

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
    CDSE_STAC_URL,
    CLMS_LAYERS,
    COPERNICUS_DIR,
    CRS_AUSTRIA,
    DOWNLOAD_BBOX,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# STAC-Katalog erkunden
# ---------------------------------------------------------------------------

def open_cdse_catalog() -> Client:
    """Öffnet den CDSE STAC-Katalog (kein Login für Metadaten nötig)."""
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


# Standard CLMS-Collections für Europa im CDSE STAC-Katalog (Pan-European VLCC / High Resolution Layers)
DEFAULT_CLMS_COLLECTIONS: list[str] = [
    "clms_vlcc_tree-cover-density_europe_10m_yearly_v1",
    "clms_vlcc_grassland_europe_10m_yearly_v1",
    "clms_vlcc_forest-type_europe_10m_3yearly_v1",
    "clms_vlcc_dominant-leaf-type_europe_10m_yearly_v1",
]


def search_clms_items(
    catalog: Client,
    bbox: list[float] | None = None,
    datetime_range: str = "2021-01-01/2023-12-31",
    collections: list[str] | None = None,
    max_items: int = 50,
) -> list:
    """Sucht CLMS-Items im STAC-Katalog für das angegebene Gebiet.

    Args:
        catalog: Geöffneter CDSE STAC-Client
        bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
        datetime_range: ISO8601 Zeitraum, z.B. "2021-01-01/2023-12-31"
        collections: Liste der STAC-Collection-IDs (Standard: DEFAULT_CLMS_COLLECTIONS)
        max_items: Maximale Anzahl zurückgegebener Items pro Collection

    Returns:
        Liste der gefundenen STAC-Items
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


def print_item_summary(items: list) -> None:
    """Gibt eine übersichtliche Tabelle der gefundenen STAC-Items aus."""
    if not items:
        print("Keine Items gefunden.")
        return

    print(f"\n{'ID':<50} {'Datum':<12} {'Assets':<30}")
    print("-" * 95)
    for item in items:
        date = item.datetime.strftime("%Y-%m-%d") if item.datetime else "N/A"
        assets = ", ".join(list(item.assets.keys())[:5])
        print(f"{item.id[:48]:<50} {date:<12} {assets:<30}")


# ---------------------------------------------------------------------------
# CLMS direkt über WCS/HTTP herunterladen (Alternative zu STAC-Assets)
# ---------------------------------------------------------------------------

# Copernicus Land Monitoring Service bietet voraggregierte Produkte teils
# auch direkt als Download-Links an. Wir implementieren beide Wege.

CLMS_DIRECT_PRODUCTS = {
    # High Resolution Layers (HRL) für Europa 2018
    # Quelle: https://land.copernicus.eu/en/products/high-resolution-layer
    "imperviousness_2018": {
        "description": "Imperviousness Density 2018 (20m, Europa)",
        "url": "https://land.copernicus.eu/api/CEMS_HRL_IMD__europe_20m_2018",
        "local_name": "imperviousness_density_2018.tif",
    },
}


# ---------------------------------------------------------------------------
# Download & lokales Speichern als COG
# ---------------------------------------------------------------------------

def download_and_clip_raster(
    href: str,
    bbox: list[float],
    output_path: Path,
    target_crs: str = CRS_AUSTRIA,
) -> Path:
    """Lädt ein Raster (COG oder GeoTIFF) herunter, schneidet es zu und speichert es.

    Unterstützt HTTP Range Requests für COGs — lädt nur den benötigten Ausschnitt.

    Args:
        href: URL oder lokaler Pfad zur Quell-Datei
        bbox: Ziel-BBox [min_lon, min_lat, max_lon, max_lat] in WGS84
        output_path: Ausgabepfad für die geclippe COG-Datei
        target_crs: Ziel-CRS für Reprojektion (Standard: Austrian Lambert)

    Returns:
        Pfad zur gespeicherten Datei
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Lade Raster: %s", href)
    logger.info("Clip auf BBox: %s → CRS: %s", bbox, target_crs)

    global rioxarray, xr
    if xr is None or rioxarray is None:
        import rioxarray as _rxr  # noqa: F401
        import xarray as _xr

        rioxarray = _rxr
        xr = _xr

    # Raster via rioxarray öffnen (unterstützt http://, s3://, lokal)
    ds: xr.DataArray = rioxarray.open_rasterio(
        href,
        chunks={"x": 2048, "y": 2048},  # Lazy loading / Dask
        lock=False,
    )

    # Clip auf BBox (in WGS84 = EPSG:4326)
    ds_clipped = ds.rio.clip_box(
        minx=bbox[0],
        miny=bbox[1],
        maxx=bbox[2],
        maxy=bbox[3],
        crs="EPSG:4326",
    )

    # Ins Ziel-CRS reprojizieren (metrisch für Österreich)
    if target_crs and ds_clipped.rio.crs and str(ds_clipped.rio.crs) != target_crs:
        ds_clipped = ds_clipped.rio.reproject(target_crs)

    # Als Cloud Optimized GeoTIFF (COG) speichern
    ds_clipped.rio.to_raster(
        str(output_path),
        driver="COG",
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info("✅ Gespeichert: %s (%.1f MB)", output_path, size_mb)
    return output_path


def download_all_clms_layers(
    stac_items: list,
    bbox: list[float] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Lädt alle CLMS-Layer für das Testgebiet herunter.

    Args:
        stac_items: Gefundene STAC-Items (aus search_clms_items)
        bbox: Clip-BBox in WGS84
        output_dir: Ausgabeverzeichnis (Standard: COPERNICUS_DIR)

    Returns:
        Dict layer_name → lokaler Dateipfad
    """
    bbox = bbox or DOWNLOAD_BBOX
    output_dir = output_dir or COPERNICUS_DIR

    downloaded: dict[str, Path] = {}

    for layer_key, layer_info in CLMS_LAYERS.items():
        output_path = output_dir / layer_info["filename"]

        if output_path.exists():
            logger.info("Layer '%s' bereits vorhanden: %s", layer_key, output_path)
            downloaded[layer_key] = output_path
            continue

        # Passendes STAC-Item für diesen Layer finden
        matching_item = _find_matching_item(stac_items, layer_key)
        if matching_item is None:
            logger.warning("Kein STAC-Item für Layer '%s' gefunden", layer_key)
            continue

        # Asset-URL extrahieren (CDSE verwendet 'data' oder 'download' als Asset-Key)
        asset_href = _get_asset_href(matching_item)
        if asset_href is None:
            logger.warning("Kein Download-Asset in Item '%s'", matching_item.id)
            continue

        downloaded[layer_key] = download_and_clip_raster(
            href=asset_href,
            bbox=bbox,
            output_path=output_path,
        )

    return downloaded


def _find_matching_item(items: list, layer_key: str):
    """Findet das STAC-Item das einem CLMS-Layer entspricht."""
    layer_keywords = {
        "imperviousness": ["IMD", "Imperviousness", "imperviousness"],
        "tree_cover": ["TCD", "Tree", "tree_cover"],
        "grassland": ["GRA", "Grassland", "grassland"],
        "water_wetness": ["WAW", "Water", "Wetness", "wetness"],
    }
    keywords = layer_keywords.get(layer_key, [layer_key])

    for item in items:
        title = item.properties.get("title", "") + item.id
        if any(kw.lower() in title.lower() for kw in keywords):
            return item
    return None


def _get_asset_href(item) -> str | None:
    """Extrahiert die Download-URL aus einem STAC-Item."""
    preferred_keys = ["data", "download", "asset", "visual"]
    for key in preferred_keys:
        if key in item.assets:
            return item.assets[key].href
    # Fallback: erstes Asset
    if item.assets:
        return next(iter(item.assets.values())).href
    return None


# ---------------------------------------------------------------------------
# CDSE Alternative: WCS (Web Coverage Service) für CLMS High-Resolution Layers
# ---------------------------------------------------------------------------

def download_clms_via_wcs(
    layer: str,
    bbox: list[float],
    output_path: Path,
    resolution_m: int = 100,
) -> Path:
    """Lädt CLMS-Layer via WCS-Request vom Copernicus Land Service.

    Für die voraggregierten HRL-Produkte (nicht Sentinel-Rohdaten) ist der
    WCS-Endpunkt oft direkter als STAC.

    Args:
        layer: Layer-ID, z.B. 'IMD_2018', 'TCD_2018'
        bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
        output_path: Ausgabepfad
        resolution_m: Gewünschte Auflösung in Metern

    Returns:
        Pfad zur gespeicherten Datei
    """
    # WCS Base-URL für CLMS HRL
    wcs_base = "https://image.discomap.eea.europa.eu/arcgis/services/GioLand"

    # Layer-URL-Mapping (EEA DiscoMap WCS)
    layer_urls = {
        "IMD_2018": f"{wcs_base}/IMD_2018/ImageServer/WCSServer",
        "TCD_2018": f"{wcs_base}/TCD_2018/ImageServer/WCSServer",
        "GRA_2018": f"{wcs_base}/GRA_2018/ImageServer/WCSServer",
        "WAW_2018": f"{wcs_base}/WAW_2018/ImageServer/WCSServer",
    }

    if layer not in layer_urls:
        raise ValueError(f"Unbekannter Layer: {layer}. Verfügbar: {list(layer_urls)}")

    # WCS GetCoverage Request
    params = {
        "SERVICE": "WCS",
        "VERSION": "1.0.0",
        "REQUEST": "GetCoverage",
        "COVERAGE": "1",
        "CRS": "EPSG:4326",
        "BBOX": ",".join(str(x) for x in bbox),
        "WIDTH": str(int((bbox[2] - bbox[0]) * 111320 / resolution_m)),
        "HEIGHT": str(int((bbox[3] - bbox[1]) * 111320 / resolution_m)),
        "FORMAT": "GeoTIFF",
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("WCS-Request für Layer '%s': %s", layer, layer_urls[layer])
    response = requests.get(layer_urls[layer], params=params, timeout=120, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info("✅ WCS-Download: %s (%.1f MB)", output_path, size_mb)
    return output_path
