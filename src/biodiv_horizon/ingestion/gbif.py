"""GBIF (Global Biodiversity Information Facility) — Artvorkommen-Ingestion.

Workflow:
1. pygbif für programmatischen API-Zugriff nutzen
2. Occurrence-Daten für Leitarten in Österreich abfragen
3. Datenqualitäts-Filterung (Koordinatengenauigkeit, Beobachtungstyp)
4. Als GeoParquet speichern (DuckDB-kompatibel)

GBIF API Doku: https://www.gbif.org/developer/occurrence
pygbif Doku:   https://pygbif.readthedocs.io/
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from biodiv_horizon.config import (
    GBIF_DIR,
    GBIF_EMAIL,
    GBIF_PASSWORD,
    GBIF_QUALITY_FILTERS,
    GBIF_USERNAME,
    LEITARTEN,
    PROCESSED_DIR,
    TEST_AREA_BBOX,
)

logger = logging.getLogger(__name__)

# GBIF Taxon Keys für Schnellzugriff
TAXON_KEYS = {info["common_name_de"]: info["taxon_key"] for info in LEITARTEN.values()}
TAXON_TO_SPECIES = {info["taxon_key"]: species for species, info in LEITARTEN.items()}


# ---------------------------------------------------------------------------
# Occurrence-Suche via pygbif
# ---------------------------------------------------------------------------

def fetch_occurrences_search(
    taxon_key: int,
    bbox: list[float] | None = None,
    year_range: str = "2018,2026",
    limit: int = 300,
    offset: int = 0,
) -> dict:
    """Fragt GBIF-Vorkommen via Occurrence Search API ab (max. 300/Request).

    Für größere Abfragen: fetch_occurrences_bulk() verwenden.

    Args:
        taxon_key: GBIF Taxon Key der Art
        bbox: [min_lon, min_lat, max_lon, max_lat] für räumlichen Filter
        year_range: z.B. "2018,2026"
        limit: Anzahl Records pro Request (max. 300)
        offset: Paging-Offset

    Returns:
        Raw GBIF API Response als dict
    """
    from pygbif import occurrences as occ

    params = {
        "taxonKey": taxon_key,
        "country": GBIF_QUALITY_FILTERS["country"],
        "year": year_range,
        "hasCoordinate": True,
        "hasGeospatialIssue": False,
        "limit": min(limit, 300),  # GBIF Maximum
        "offset": offset,
    }

    # Optionaler Bounding-Box-Filter
    if bbox:
        # GBIF verwendet WKT für räumliche Filter via geometry-Parameter
        min_lon, min_lat, max_lon, max_lat = bbox
        params["geometry"] = (
            f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
            f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        )

    logger.debug("GBIF-Request: taxonKey=%d, offset=%d", taxon_key, offset)
    return occ.search(**params)


def fetch_all_occurrences(
    taxon_key: int,
    bbox: list[float] | None = None,
    year_range: str = "2018,2026",
    max_records: int = 10000,
    sleep_between_pages: float = 0.5,
) -> gpd.GeoDataFrame:
    """Lädt alle GBIF-Vorkommen einer Art mit automatischem Paging.

    Args:
        taxon_key: GBIF Taxon Key
        bbox: Optionaler räumlicher Filter
        year_range: Zeitraum-Filter
        max_records: Maximale Anzahl Records (Sicherheitsgrenze)
        sleep_between_pages: Pause zwischen API-Calls (API-Fairness)

    Returns:
        GeoDataFrame mit allen Vorkommen
    """
    species_name = TAXON_TO_SPECIES.get(taxon_key, f"taxon_{taxon_key}")
    logger.info("Lade GBIF-Daten für: %s (taxonKey=%d)", species_name, taxon_key)

    all_records = []
    offset = 0
    page_size = 300

    while offset < max_records:
        response = fetch_occurrences_search(
            taxon_key=taxon_key,
            bbox=bbox,
            year_range=year_range,
            limit=min(page_size, max_records - offset),
            offset=offset,
        )

        records = response.get("results", [])
        if not records:
            break

        all_records.extend(records)
        total = response.get("count", 0)
        end_of_records = response.get("endOfRecords", True)

        logger.info(
            "  Page %d: +%d Records (gesamt: %d / %d)",
            offset // page_size + 1,
            len(records),
            len(all_records),
            total,
        )

        if end_of_records or len(all_records) >= max_records:
            break

        offset += page_size
        time.sleep(sleep_between_pages)

    logger.info("✅ %d Vorkommen geladen für %s", len(all_records), species_name)
    return _records_to_geodataframe(all_records, species_name)


# ---------------------------------------------------------------------------
# Datenqualitäts-Filterung & GeoDataFrame-Konvertierung
# ---------------------------------------------------------------------------

def _records_to_geodataframe(records: list[dict], species_name: str) -> gpd.GeoDataFrame:
    """Konvertiert GBIF-Records in ein bereinigtes GeoDataFrame."""
    if not records:
        return gpd.GeoDataFrame(columns=_get_output_columns(), geometry="geometry", crs="EPSG:4326")

    rows = []
    skipped = 0

    for r in records:
        lat = r.get("decimalLatitude")
        lon = r.get("decimalLongitude")

        # Koordinaten-Pflichtcheck
        if lat is None or lon is None:
            skipped += 1
            continue

        # Plausibilitätscheck für Österreich
        if not (46.0 <= lat <= 49.5 and 9.0 <= lon <= 18.0):
            skipped += 1
            continue

        rows.append({
            "gbif_id": r.get("gbifID"),
            "species": species_name,
            "taxon_key": r.get("taxonKey"),
            "common_name": r.get("vernacularName", ""),
            "latitude": lat,
            "longitude": lon,
            "coordinate_uncertainty_m": r.get("coordinateUncertaintyInMeters"),
            "year": r.get("year"),
            "month": r.get("month"),
            "day": r.get("day"),
            "basis_of_record": r.get("basisOfRecord"),
            "institution": r.get("institutionCode", ""),
            "dataset": r.get("datasetName", ""),
            "country_code": r.get("countryCode"),
            "state_province": r.get("stateProvince", ""),
            "geometry": Point(lon, lat),
        })

    if skipped > 0:
        logger.warning("  %d Records übersprungen (keine/ungültige Koordinaten)", skipped)

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    logger.info("  GeoDataFrame: %d Records, %d Spalten", len(gdf), len(gdf.columns))
    return gdf


def _get_output_columns() -> list[str]:
    return [
        "gbif_id", "species", "taxon_key", "common_name",
        "latitude", "longitude", "coordinate_uncertainty_m",
        "year", "month", "day", "basis_of_record",
        "institution", "dataset", "country_code", "state_province",
    ]


# ---------------------------------------------------------------------------
# Alle Leitarten laden & als GeoParquet speichern
# ---------------------------------------------------------------------------

def fetch_all_leitarten(
    bbox: list[float] | None = None,
    output_path: Path | None = None,
    max_records_per_species: int = 10000,
) -> gpd.GeoDataFrame:
    """Lädt GBIF-Daten für alle konfigurierten Leitarten.

    Args:
        bbox: Optionaler räumlicher Filter (Standard: ganz Österreich)
        output_path: GeoParquet-Ausgabepfad (Standard: PROCESSED_DIR)
        max_records_per_species: Maximale Records pro Art

    Returns:
        Kombiniertes GeoDataFrame aller Leitarten
    """
    output_path = output_path or (PROCESSED_DIR / "species_occurrences.parquet")

    all_gdfs = []
    for species_name, info in LEITARTEN.items():
        gdf = fetch_all_occurrences(
            taxon_key=info["taxon_key"],
            bbox=bbox,
            max_records=max_records_per_species,
        )
        if not gdf.empty:
            gdf["color"] = info["color"]
            gdf["emoji"] = info["emoji"]
            gdf["habitat"] = info["habitat"]
            gdf["ffh_species"] = info["ffh"]
            all_gdfs.append(gdf)

    if not all_gdfs:
        logger.warning("Keine Daten geladen!")
        return gpd.GeoDataFrame()

    combined = gpd.GeoDataFrame(pd.concat(all_gdfs, ignore_index=True), crs="EPSG:4326")

    # Als GeoParquet speichern
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(str(output_path))

    logger.info(
        "✅ Gespeichert: %s (%d Records, %d Arten)",
        output_path,
        len(combined),
        combined["species"].nunique(),
    )
    return combined


# ---------------------------------------------------------------------------
# Statistik & Qualitätsprüfung
# ---------------------------------------------------------------------------

def print_occurrence_stats(gdf: gpd.GeoDataFrame) -> None:
    """Gibt eine Übersichts-Statistik des GeoDataFrame aus."""
    if gdf.empty:
        print("Kein Daten vorhanden.")
        return

    print(f"\n📊 GBIF Occurrence Statistik")
    print(f"   Gesamt Records: {len(gdf):,}")
    print(f"   Zeitraum: {gdf['year'].min()} – {gdf['year'].max()}")
    print()
    print("   Pro Art:")
    for species, group in gdf.groupby("species"):
        info = next((v for v in LEITARTEN.values() if v["common_name_de"] in species
                     or species in LEITARTEN), {})
        emoji = info.get("emoji", "•")
        uncertainty = group["coordinate_uncertainty_m"].median()
        print(
            f"   {emoji} {species}: {len(group):>5,} Records "
            f"| Median Unsicherheit: {uncertainty:.0f}m "
            f"| Jahre: {group['year'].min()}–{group['year'].max()}"
        )
