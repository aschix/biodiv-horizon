"""Raster-Extraktion: Copernicus-Rasterwerte an GBIF-Fundpunkten samplen.

Workflow:
1. GeoDataFrame (GBIF-Punkte) + Raster-Dateien (Copernicus COGs) laden
2. Für jeden Punkt die Rasterwerte der 4 CLMS-Layer extrahieren
3. Angereicherte GeoDataFrame als GeoParquet speichern
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS

from biodiv_horizon.config import CLMS_LAYERS, COPERNICUS_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)


def extract_raster_values_at_points(
    gdf: gpd.GeoDataFrame,
    raster_path: Path,
    column_name: str,
    nodata_value: float = np.nan,
) -> gpd.GeoDataFrame:
    """Extrahiert Rasterwerte an den Punktpositionen des GeoDataFrame.

    Reproiziert die Punkte automatisch ins Raster-CRS.

    Args:
        gdf: GeoDataFrame mit Point-Geometrien
        raster_path: Pfad zur Raster-Datei (COG oder GeoTIFF)
        column_name: Name der neuen Spalte für die Rasterwerte
        nodata_value: Wert für NoData-Pixel (Standard: NaN)

    Returns:
        GeoDataFrame mit neuer Spalte für Rasterwerte
    """
    gdf = gdf.copy()

    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        nodata = src.nodata

        # Punkte ins Raster-CRS reprojizieren
        points_reproj = gdf.to_crs(raster_crs)
        coords = [(p.x, p.y) for p in points_reproj.geometry]

        # Rasterwerte samplen (Band 1)
        values = list(src.sample(coords, indexes=1))

    # NoData-Werte durch nodata_value ersetzen
    extracted = []
    for v in values:
        val = float(v[0]) if v else np.nan
        if nodata is not None and val == nodata:
            val = nodata_value
        extracted.append(val)

    gdf[column_name] = extracted
    valid_count = sum(1 for v in extracted if not np.isnan(v))
    logger.info(
        "Extrahiert '%s': %d/%d Punkte haben Werte",
        column_name,
        valid_count,
        len(gdf),
    )
    return gdf


def enrich_with_all_clms_layers(
    gdf: gpd.GeoDataFrame,
    clms_dir: Path | None = None,
    output_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Reichert alle GBIF-Punkte mit den 4 CLMS-Rasterlayern an.

    Args:
        gdf: GeoDataFrame mit GBIF-Vorkommen
        clms_dir: Verzeichnis mit den COG-Dateien (Standard: COPERNICUS_DIR)
        output_path: Ausgabepfad für angereichertes GeoParquet

    Returns:
        Angereichertes GeoDataFrame
    """
    clms_dir = clms_dir or COPERNICUS_DIR
    output_path = output_path or (PROCESSED_DIR / "species_enriched.parquet")

    for layer_key, layer_info in CLMS_LAYERS.items():
        raster_path = clms_dir / layer_info["filename"]
        if not raster_path.exists():
            logger.warning("CLMS-Layer nicht gefunden: %s", raster_path)
            gdf[layer_key] = np.nan
            continue

        gdf = extract_raster_values_at_points(
            gdf=gdf,
            raster_path=raster_path,
            column_name=layer_key,
        )

    # Speichern
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(str(output_path))
    logger.info("✅ Angereichertes GeoParquet: %s (%d Records)", output_path, len(gdf))
    return gdf
