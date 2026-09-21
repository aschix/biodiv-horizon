# Copernicus Data Access Guide – BioDiv-Horizon

> **Zweck dieses Dokuments:** Referenz-Guide für alle Copernicus-Zugangswege im Projekt.
> Beantwortet: *Welche Clients existieren? Was setzen wir ein und warum?*

---

## 1. Das Ökosystem auf einen Blick

| Client | Zweck | Status in BioDiv-Horizon |
|:---|:---|:---|
| `pystac-client` | STAC-Katalog durchsuchen (Metadaten + URLs) | ✅ Sprint 1 + 2+ |
| `rioxarray` / `rasterio` | COG-Streaming & Rasterverarbeitung | ✅ Sprint 2a → Standard ab Sprint 2b |
| `OWSLib` | OGC-konforme WCS/WFS/WMS-Server | 🔜 Zukunft (andere OGC-Dienste) |
| `openeo` | Cloud-native Processing direkt auf CDSE | 🔜 Phase 2 (NDVI-Zeitreihen, Mosaike) |
| `eodag` | Multi-Provider-Abstraktionsschicht | 🔜 Zukunft (US Landsat, Sentinel Hub) |
| `requests` | Fallback für proprietäre REST-APIs (EEA ArcGIS) | ✅ Sprint 2a (Lernzweck), bleibt für EEA |

---

## 2. Die Clients im Detail

### A. `pystac-client` — STAC-Katalog-Navigation

**Was es ist:** Python-Client für den OGC STAC-Standard (SpatioTemporal Asset Catalog).  
**Anwendungsfall:** Katalog durchsuchen — *"Welche CLMS-Layer gibt es für die Donau-Auen im Jahr 2018?"*  
**Was es NICHT macht:** Download und Verarbeitung der Rasterdaten (nur Metadaten + Asset-URLs).

```python
from pystac_client import Client

cdse = Client.open("https://catalogue.dataspace.copernicus.eu/stac")
results = cdse.search(collections=["CLMS_TCD_2018"], bbox=donau_auen_bbox)
items = list(results.items())  # Liste von STAC Items (Metadaten + Download-URLs)
```

---

### B. `rioxarray` + `rasterio` — Raster-Streaming & Verarbeitung

**Was es ist:** `rasterio` = C-Bibliothek (libgdal-Wrapper) für GeoTIFF/COG-I/O; `rioxarray` = xarray-Extension.  
**Stärke:** Kein Download der Gesamtdatei nötig — HTTP Range Requests laden nur den benötigten Ausschnitt.

```python
import rioxarray as rxr

# Lädt NUR die Kacheln für Donau-Auen via HTTP Range Request (Cloud Optimized GeoTIFF)
ds = rxr.open_rasterio("https://...clms_tcd_2018.tif", chunks={"x": 2048, "y": 2048})
clipped = ds.rio.clip_box(*donau_auen_bbox, crs="EPSG:4326")
clipped.rio.to_raster("tcd_donau_auen.tif", driver="COG")
```

---

### C. `OWSLib` — OGC-Standards (WCS, WFS, WMS)

**Was es ist:** Das OSGeo-Standardpaket für alle OGC-konformen Web-Services.  
**Problem EEA DiscoMap:** EEA nutzt ArcGIS — WCS-Modul ist deaktiviert (HTTP 400). OWSLib hier nicht nutzbar.  
**Wo sinnvoll:** Andere OGC-konforme Dienste (Bundesforste-WCS, Austria-WFS, INSPIRE-Dienste).

```python
from owslib.wcs import WebCoverageService

wcs = WebCoverageService("https://example.org/ows", version="2.0.1")
response = wcs.getCoverage(
    identifier=["my_layer"],
    bbox=(16.5, 48.08, 16.95, 48.22),
    crs="EPSG:4326",
    format="image/tiff",
)
with open("layer.tif", "wb") as f:
    f.write(response.read())
```

---

### D. `openeo` — Cloud-Native Processing (EU/ESA-Standard)

**Was es ist:** Offizieller EU/ESA-Standard für Cloud-native Erdbeobachtungsverarbeitung (maßgeblich entwickelt an TU Wien + EODC).  
**Prinzip:** "Bring the Code to the Data" — Analyse läuft auf CDSE-Servern, nur das Ergebnis wird heruntergeladen.  
**Wann:** Phase 2 (NDVI-Zeitreihen, Wolkenfilterung, Mosaikierung über mehrere Jahre).

```python
import openeo

conn = openeo.connect("https://openeo.dataspace.copernicus.eu")
conn.authenticate_oidc()  # CDSE-Account

cube = conn.load_collection(
    "SENTINEL2_L2A",
    spatial_extent={"west": 16.5, "south": 48.08, "east": 16.95, "north": 48.22},
    temporal_extent=["2023-06-01", "2023-08-31"],
    bands=["B04", "B08"],
)
red, nir = cube.band("B04"), cube.band("B08")
ndvi = (nir - red) / (nir + red)
ndvi.reduce_dimension("t", reducer="median").download("ndvi_sommer_2023.tif")
```

---

### E. `eodag` (Earth Observation Data Access Gateway)

**Was es ist:** Abstraktionsschicht über ~30 Satellite-Imagery-Provider (CDSE, AWS, USGS Landsat, Sentinel Hub ...).  
**Wann:** Wenn Vergleichsanalysen mit US-Landsat oder anderen Satellitendaten geplant sind.

---

## 3. Was setzen wir ein und warum?

### Entscheidungsmatrix BioDiv-Horizon Phase 1

| Aufgabe | Sprint 2a | Sprint 2b+ | Begründung |
|:---|:---|:---|:---|
| CDSE Katalog durchsuchen | `pystac-client` | `pystac-client` | Standard, kein besseres Tool |
| CLMS-Layer (STAC-URL) | **eigene `requests`-Schleife** | **`rioxarray.open_rasterio(url)`** | 2a: Lernzweck; 2b: effizienter (COG-Streaming) |
| EEA DiscoMap (Imperv., Wetness) | **`requests.get()`** | **`requests.get()`** bleibt | OWSLib nicht nutzbar; ArcGIS REST ist proprietär |
| NDVI-Zeitreihen | — | **`openeo`** | Cloud-Processing (Phase 2) |
| OGC-WCS anderer Server | — | **`owslib`** | Standard-Client für echte OGC-Dienste |
| Multi-Provider (Zukunft) | — | **`eodag`** | Landsat, Sentinel Hub etc. |

### Warum Sprint 2a bewusst ohne Standard-Clients?

> [!NOTE]
> **Lernziel Sprint 2a:** Wer versteht, wie ein HTTP Range Request gegen einen COG-Endpoint funktioniert, versteht danach sofort *warum* `rioxarray.open_rasterio(url)` so effizient ist. Ein fertiger Client verbirgt dieses Wissen. Nach Sprint 2a bist du in der Lage, jeden Geodaten-Client zu debuggen, weil du die zugrundeliegenden HTTP-Mechanismen kennst.

Das entspricht dem Lernprinzip aus dem **AutoGIS-Kurs** der Universität Helsinki: erst manuell verstehen, dann automatisieren.

---

## 4. Layer-Quellen

| CLMS-Layer | Sprint 2a | Sprint 2b | Auflösung |
|:---|:---|:---|:---|
| Tree Cover Density (TCD 2018) | CDSE STAC → manueller Download | CDSE STAC → `rioxarray` COG-Streaming | 10m |
| Grassland (GRA 2018) | CDSE STAC → manueller Download | CDSE STAC → `rioxarray` COG-Streaming | 10m |
| Forest Type (FTY 2018) | CDSE STAC → manueller Download | CDSE STAC → `rioxarray` COG-Streaming | 10m |
| Imperviousness (IMD 2018) | EEA REST `exportImage` | EEA REST `exportImage` | 10m (via ArcGIS) |
| Water & Wetness (WAW 2018) | EEA REST `exportImage` | EEA REST `exportImage` | 10m (via ArcGIS) |

---

## 5. Bekannte Tücken & Workarounds

### EEA DiscoMap: OGC WCS deaktiviert
```
GET https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/
    HRL_ImperviousnessDensity_2018/ImageServer/exportImage?
    bbox=16.5,48.08,16.95,48.22&bboxSR=4326&format=tiff&f=image
```
Dieser Endpunkt liefert direkt binäre GeoTIFF-Daten. OWSLib gibt hier HTTP 400 zurück.

### CDSE STAC: CLMS-Collections noch im Aufbau
Nicht alle CLMS-Layer sind bereits als eigenständige STAC-Collections auf CDSE verfügbar (Stand: 2026).
Fallback: EEA DiscoMap (siehe oben).

### COG-Streaming: Authentifizierung für geschützte CDSE-Daten
```python
import os
os.environ["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {access_token}"
```
Für öffentliche CLMS-Layer ist keine Authentifizierung erforderlich.

---

## 6. Weiterführende Links

| Ressource | URL |
|:---|:---|
| CDSE STAC Browser | https://catalogue.dataspace.copernicus.eu/stac |
| CLMS Portal (EEA) | https://land.copernicus.eu/en/products |
| EEA DiscoMap GioLandPublic Services | https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic |
| openEO CDSE | https://openeo.dataspace.copernicus.eu |
| OWSLib Dokumentation | https://owslib.readthedocs.io |
| eodag Dokumentation | https://eodag.readthedocs.io |
| pystac-client Dokumentation | https://pystac-client.readthedocs.io |
| AutoGIS 2025 | https://autogis-site.readthedocs.io |
