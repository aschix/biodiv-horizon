"""Zentrale Konfiguration: Pfade, Bounding Boxes, Leitarten, STAC-Endpoints."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Verzeichnisse ---
ROOT_DIR = Path(__file__).parent.parent.parent  # Projekt-Root
DATA_DIR = ROOT_DIR / os.getenv("DATA_DIR", "data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
TILES_DIR = DATA_DIR / "tiles"

# Unterverzeichnisse Roh-Daten
COPERNICUS_DIR = RAW_DIR / "copernicus"
GBIF_DIR = RAW_DIR / "gbif"
ADMIN_DIR = RAW_DIR / "admin"

# Alle Verzeichnisse automatisch anlegen
for _d in [COPERNICUS_DIR, GBIF_DIR, ADMIN_DIR, PROCESSED_DIR, TILES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# --- CDSE / Copernicus ---
CDSE_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
CDSE_USERNAME = os.getenv("CDSE_USERNAME", "")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD", "")

# --- GBIF ---
GBIF_USERNAME = os.getenv("GBIF_USERNAME", "")
GBIF_PASSWORD = os.getenv("GBIF_PASSWORD", "")
GBIF_EMAIL = os.getenv("GBIF_EMAIL", "")

# --- Testgebiet: Nationalpark Donau-Auen ---
# Bounding Box: [min_lon, min_lat, max_lon, max_lat] (WGS84 / EPSG:4326)
TEST_AREA_BBOX: list[float] = [
    float(x) for x in os.getenv("TEST_AREA_BBOX", "16.5,48.08,16.95,48.22").split(",")
]
TEST_AREA_NAME = os.getenv("TEST_AREA_NAME", "Nationalpark Donau-Auen")

# Erweitertes Testgebiet (Puffer für Download, dann zuschneiden)
DOWNLOAD_BBOX: list[float] = [
    TEST_AREA_BBOX[0] - 0.05,
    TEST_AREA_BBOX[1] - 0.05,
    TEST_AREA_BBOX[2] + 0.05,
    TEST_AREA_BBOX[3] + 0.05,
]

# --- Koordinatensystem ---
CRS_WGS84 = "EPSG:4326"          # Eingabe-CRS (GBIF, STAC-Suche)
CRS_AUSTRIA = "EPSG:31287"       # MGI / Austria Lambert (metrisch, für Analysen)
CRS_WEB_MERCATOR = "EPSG:3857"   # Web Mercator (für Tile-Serving)

# --- Leitarten (GBIF Taxon Keys) ---
LEITARTEN: dict[str, dict] = {
    "Lepus europaeus": {
        "taxon_key": 2436775,
        "common_name_de": "Feldhase",
        "emoji": "🐰",
        "color": "#F59E0B",        # Warm Gold
        "habitat": "Offenland / Grünland",
        "ffh": False,
    },
    "Phasianus colchicus": {
        "taxon_key": 9515886,
        "common_name_de": "Fasan",
        "emoji": "🦆",
        "color": "#B45309",        # Kupferrot
        "habitat": "Agrarlandschaft / Feldgehölze",
        "ffh": False,
    },
    "Vanessa atalanta": {
        "taxon_key": 1898286,
        "common_name_de": "Admiral",
        "emoji": "🦋",
        "color": "#7C3AED",        # Violett
        "habitat": "Halboffenland / Säume",
        "ffh": False,
    },
    "Lanius collurio": {
        "taxon_key": 2490450,
        "common_name_de": "Neuntöter",
        "emoji": "🐦",
        "color": "#0D9488",        # Teal
        "habitat": "Halboffenland / Hecken",
        "ffh": True,               # FFH-Anhang I
    },
}

# --- Copernicus CLMS Layer-Definitionen (Single Source of Truth) ---
CLMS_LAYERS: dict[str, dict] = {
    "tree_cover": {
        "description": "Baumbestand / Tree Cover Density (%)",
        "unit": "%",
        "range": (0, 100),
        "colormap": "Greens",
        "filename": "tree_cover_density.tif",
        "source": "stac",
        "stac_collection": "clms_vlcc_tree-cover-density_europe_10m_yearly_v1",
        "wcs_layer": "TCD_2018",
    },
    "grassland": {
        "description": "Grünland (binär: 0/1)",
        "unit": "binär",
        "range": (0, 1),
        "colormap": "YlGn",
        "filename": "grassland.tif",
        "source": "stac",
        "stac_collection": "clms_vlcc_grassland_europe_10m_yearly_v1",
        "wcs_layer": "GRA_2018",
    },
    "forest_type": {
        "description": "Waldtyp (Laub-/Nadel-/Mischwald)",
        "unit": "Klassen",
        "range": (1, 3),
        "colormap": "Dark2",
        "filename": "forest_type.tif",
        "source": "stac",
        "stac_collection": "clms_vlcc_forest-type_europe_10m_3yearly_v1",
        "wcs_layer": None,
    },
    "imperviousness": {
        "description": "Versiegelungsgrad (%)",
        "unit": "%",
        "range": (0, 100),
        "colormap": "Reds",
        "filename": "imperviousness_density.tif",
        "source": "wcs",
        "stac_collection": None,  # Auf CDSE STAC nicht als Einzel-Layer -> EEA WCS
        "wcs_layer": "IMD_2018",
    },
    "water_wetness": {
        "description": "Wasserflächen & Feuchtgebiete (binär: 0/1)",
        "unit": "binär",
        "range": (0, 1),
        "colormap": "Blues",
        "filename": "water_wetness.tif",
        "source": "wcs",
        "stac_collection": None,  # Auf CDSE STAC unvollständig -> EEA WCS
        "wcs_layer": "WAW_2018",
    },
}

# --- Datenqualität GBIF ---
GBIF_QUALITY_FILTERS = {
    "hasCoordinate": True,
    "hasGeospatialIssue": False,
    "coordinateUncertaintyInMeters": "0,1000",  # max. 1km Unsicherheit
    "basisOfRecord": [
        "HUMAN_OBSERVATION",
        "MACHINE_OBSERVATION",
        "PRESERVED_SPECIMEN",
    ],
    "year": "2018,2026",
    "country": "AT",
}
