# BioDiv-Horizon

**Interaktiver Open-Source-Prototyp:** Copernicus-Umweltdaten (CLMS) + GBIF-Artvorkommen räumlich verknüpft und auf einer 3D-Karte Österreichs erforschbar.

## Projektziel

Dieses Projekt demonstriert eine leichtgewichtige Geodaten-Pipeline die:
- **Copernicus Land Monitoring Service (CLMS)** Daten via STAC API abruft (Versiegelung, Baumbestand, Grünland, Feuchtgebiete)
- **GBIF-Artvorkommen** für österreichische Leitarten abfragt (Feldhase, Fasan, Admiral-Schmetterling, Neuntöter)
- Raster- und Vektordaten **räumlich verschneidet** und als GeoParquet speichert
- Die Daten über eine **FastAPI** bereitstellt
- Interaktiv auf einer **MapLibre GL JS + deck.gl** Karte visualisiert

## Tech-Stack

| Schicht | Technologie |
|:---|:---|
| Datenquellen | Copernicus CDSE (STAC), GBIF API, data.gv.at (OGD) |
| Ingestion | `pystac-client`, `rasterio`, `rioxarray`, `pygbif` |
| Storage | DuckDB Spatial, GeoParquet, Cloud Optimized GeoTIFF |
| Analytics | `geopandas`, `rasterstats`, `duckdb` |
| Backend | FastAPI, `rio-tiler` (Tile-Serving) |
| Frontend | MapLibre GL JS, deck.gl |

## Setup

### Voraussetzungen
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) Paketmanager

### Installation

```bash
# Abhängigkeiten installieren
uv sync

# CDSE-Credentials konfigurieren
cp .env.example .env
# .env bearbeiten und CDSE_USERNAME / CDSE_PASSWORD eintragen
```

### Jupyter Notebooks starten

```bash
# Im Browser via JupyterLab
uv run python -m jupyterlab

# Oder direkt in VS Code / Antigravity IDE:
# Einfach notebooks/01_explore_cdse_stac.ipynb öffnen und den Kernel .venv (Python) auswählen.
```

### API-Server starten

```bash
uv run uvicorn biodiv_horizon.api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

## Projektstruktur

```
biodiv-horizon/
├── PLAN.md                  # Implementierungsplan (alle Sprints)
├── pyproject.toml           # Abhängigkeiten
├── .env                     # Credentials (nicht in Git!)
├── data/                    # Lokaler Data Lake (in .gitignore)
│   ├── raw/                 # Rohdaten (Copernicus, GBIF, Admin)
│   ├── processed/           # GeoParquet-Files
│   └── tiles/               # Vorberechnete Raster-Tiles
├── notebooks/               # Explorative Jupyter Notebooks (Sprint 1–4)
├── src/biodiv_horizon/      # Python-Paket
│   ├── ingestion/           # Daten-Download-Pipelines
│   ├── processing/          # Räumliche Verschneidung
│   ├── analytics/           # DuckDB-Abfragen
│   └── api/                 # FastAPI Backend
└── frontend/                # Web-Dashboard (MapLibre + deck.gl)
```

## Testgebiet

**Nationalpark Donau-Auen** (östlich von Wien)
- Bounding Box: `[16.5, 48.08, 16.95, 48.22]` (WGS84)
- Fläche: ~93 km²
- Natura2000: AT1205A00

## Leitarten

| Art | Taxon Key (GBIF) | Lebensraum-Indikator |
|:---|:---|:---|
| 🐰 Feldhase (*Lepus europaeus*) | 2436775 | Offenland / Grünland |
| 🦆 Fasan (*Phasianus colchicus*) | 9515886 | Agrarlandschaft |
| 🦋 Admiral (*Vanessa atalanta*) | 1898286 | Halboffenland / Säume |
| 🐦 Neuntöter (*Lanius collurio*) | 2490450 | FFH-Anhang I / Hecken |

## Lizenz

MIT — Open Source für netidee / FFG Projektkonsortien.
