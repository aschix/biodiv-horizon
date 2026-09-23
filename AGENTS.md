# AGENTS.md – Kontext & Arbeitsanweisungen für BioDiv-Horizon

> **Zweck dieses Dokuments:** Dieses Dokument dient als primäre Arbeitsanweisung und Wissensbasis für KI-Agenten (Antigravity, Claude Code, Cursor) in diesem Repository. Es definiert Projektziele, Architekturrichtlinien, wichtige Referenzen und die Arbeitsweise mit Daniel.

---

## 🌍 Projektüberblick: BioDiv-Horizon

**BioDiv-Horizon** ist ein leichtgewichtiger, modularer Open-Source-Prototyp und Technologie-Demonstrator:
* **Kernidee:** Räumliche Verschneidung hochauflösender **Copernicus Land Monitoring Service (CLMS)** Rasterdaten (Baumbestand, Versiegelung, Grünland, Feuchtgebiete) mit **GBIF-Biodiversitätsdaten** (Artvorkommen für österreichische Leitarten).
* **Testgebiet:** **Nationalpark Donau-Auen** (östlich von Wien, Bounding Box: `[16.5, 48.08, 16.95, 48.22]`, Natura-2000-Gebiet `AT1205A00`, Fläche ca. 93 km²).
* **Strategische Bedeutung:** Das Projekt dient als praxisnaher Proof-of-Concept für Förderanträge (z. B. *FFG AI for Green*, *FFG AI Ökosysteme 2026*, *netidee*) und als Referenzarchitektur für Partnerkonsortien (BOKU, IT:U Linz, Nationalparks Austria, Österreichische Bundesforste).

---

## 👤 Nutzerprofil & Didaktischer Leitfaden

* **Nutzer:** Dipl.-Ing. Daniel Aschauer (*bitessenz e.U.*)
* **Background:** 15+ Jahre Senior Java Enterprise Software Engineer und System-Architekt (Spring Boot, Microservices, APIs, Graph- & SQL-Datenbanken).
* **Laufende Spezialisierung:**
  * *Zertifikatslehrgang Naturschutzfachkraft (FH Kärnten)*: Biotopkartierung, FFH-Richtlinie, Natura 2000, EU Nature Restoration Law.
  * *AutoGIS 2025 (Universität Helsinki)*: Automatisierte Geodatenverarbeitung mit Python (`geopandas`, `shapely`, `rasterio`, CRS).
* **Didaktische Prämisse für Agenten:**
  * Daniel beherrscht Software-Architektur und Clean Code meisterhaft, vertieft sich jedoch gerade gezielt in den modernen **Python Geospatial Stack**.
  * **Kein Black-Box-Code:** Erkläre geodaten-spezifische Mechanismen (z. B. CRS-Transformationen, Bounding-Box-Konventionen `[minx, miny, maxx, maxy]`, WCS-Slice-Parameter, Raster-Maskierung).
  * **Schrittweises Vorgehen:** Wie in `PLAN.md` festgelegt, wird in Sprint 2a zuerst der manuelle Weg über direkte HTTP/WCS-Requests implementiert und verstanden, bevor in Sprint 2b das Refactoring auf High-Level-Libraries (`rioxarray`) erfolgt.

---

## 📚 Zentrale Referenzen & Projekt-Dokumente

Jeder Agent **muss** sich vor der Arbeit an diesen Kerndokumenten orientieren:

| Dokument / Verzeichnis | Zweck & Inhalt | Wann konsultieren? |
|:---|:---|:---|
| [PLAN.md](PLAN.md) | **Der Master-Fahrplan:** Alle Sprints (1 bis 7), detaillierte Aufgaben, Datenlayer-Listen, Zeitplan und offene Punkte. | **Zu Beginn jeder Session/Sprints** und zum Abhaken erledigter Tasks. |
| [docs/copernicus_clients.md](docs/copernicus_clients.md) | **Client-Entscheidungsmatrix:** Übersicht der 6 Zugangswege (`rioxarray`, `pystac-client`, `OWSLib`, `openeo`, `eodag`, `requests`), Code-Snippets und Sprint-2a/2b-Strategie. | Bei allen Aufgaben rund um Copernicus CLMS-Downloads. |
| [docs/copernicus_guide.md](docs/copernicus_guide.md) | **Ausführlicher Copernicus-Guide:** Ökosystem, CDSE vs. EEA DiscoMap, WCS-Eigenheiten, Layer-IDs und Troubleshooting. | Bei tiefgehenden Fragen zu CLMS-APIs oder Fehlersuche. |
| [README.md](README.md) | Schnelleinstieg, Projektstruktur, Testgebiets-Koordinaten und GBIF-Leitarten. | Für schnelle Übersichten und Setup-Befehle. |
| [notebooks/](notebooks/) | Interaktive Jupyter-Notebooks für explorative Prototypen (`01_explore_cdse_stac.ipynb`, `02a_...`, etc.). | Für interaktive Analysen und didaktische Schritte. |
| [src/biodiv_horizon/](src/biodiv_horizon/) | Das produktive Python-Paket (`ingestion`, `processing`, `analytics`, `api`). | Für modularen, getesteten Produktivcode ab Sprint 2b. |

---

## 🛠️ Technische Leitlinien & Entwickler-Regeln

### 1. Paket- & Umgebungsverwaltung
* **Ausschließlich `uv` verwenden:**
  * `uv sync` zur Synchronisation der Abhängigkeiten
  * `uv run python ...` bzw. `uv run pytest` zur Ausführung
  * `uv add <package>` zum Hinzufügen von Paketen
  * **Kein** ungefragtes `pip install` im System-Python!

### 2. Geodaten- & CRS-Handling
* **Koordinatenreferenzsysteme (CRS) immer explizit behandeln:**
  * GBIF & Web-Karten: `EPSG:4326` (WGS84, `lat/lon` bzw. `[minx, miny, maxx, maxy]`)
  * Copernicus CLMS Raster (HRL): `EPSG:3035` (ETRS89-LAEA, metrisch)
  * Österreichischer Standard (BEV): `EPSG:31256` (MGI Austria GK East) bzw. `EPSG:31287`
  * Raster niemals stillschweigend reprojizieren, sondern Resampling-Methoden (z. B. `bilinear` für stetige Werte wie Kronendach, `nearest` für diskrete Klassen wie Landbedeckung) bewusst wählen.
* **Cloud-Native Formate priorisieren:**
  * Vektordaten: **GeoParquet** (spaltenorientiert, schnell, typensicher)
  * Rasterdaten: **COG (Cloud Optimized GeoTIFF)**
  * Tabellen / Geometrie-Queries: **DuckDB Spatial**

### 3. Notebook- & Git-Hygiene
* **Keine Binär-Outputs in Git committen:**
  * Jupyter-Notebooks müssen vor Commits gecleant werden (über den in `.gitattributes` konfigurierten Filter).
  * Große Testdaten gehören in `data/raw/` bzw. `data/processed/` (bereits in `.gitignore`).
* **Secrets-Disziplin:**
  * Passwörter, Tokens und API-Keys niemals in Code oder Notebooks schreiben – ausschließlich über `.env` laden (`python-dotenv`).

### 4. Betriebssystem-Kontext
* Daniel arbeitet auf **Windows 11** mit **PowerShell (`pwsh`)**.
* Shell-Befehle und Pfade müssen Windows- und PowerShell-kompatibel sein (Forward Slashes `/` in Python-Pfaden bevorzugt).

---

## 🔄 Sprint-Workflow für neue Sessions

Wenn eine neue Konversation für einen Sprint gestartet wird:
1. **Status prüfen:** In `PLAN.md` den aktuellen Sprint und dessen Aufgaben verifizieren.
2. **Fokus definieren:** Genau die Aufgaben des Sprints anpacken (z. B. Sprint 2a: Notebook `02a_download_clms_manual.ipynb`).
3. **Abschluss & Dokumentation:** Nach Erreichen des Meilensteins `PLAN.md` abhaken, eventuelle neue Erkenntnisse in `docs/` ergänzen und saubere Git-Commits anfertigen.