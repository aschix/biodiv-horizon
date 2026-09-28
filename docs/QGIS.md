# QGIS Quickstart Guide für BioDiv-Horizon

> **Zweck:** Schnelleinstieg in die visuelle Inspektion, Qualitätsprüfung und kartographische Aufbereitung der im Projekt generierten Geodaten (Copernicus CLMS GeoTIFFs & GBIF GeoParquet).

---

## 1. Installation unter Windows

QGIS ist das führende Open-Source-Geoinformationssystem (GIS) und Industriestandard in Wissenschaft, Behörden und Planungsbüros.

### Installation via Windows Package Manager (`winget`):
Öffne ein PowerShell-Terminal:
```powershell
winget install QGIS.QGIS
```
*(Alternativ: Standalone-Installer für Windows von [qgis.org](https://qgis.org/) herunterladen. Die LTR-Version „Long Term Release“ ist besonders stabil).*

---

## 2. Erste Schritte: Projekt & Basiskarten

1. **QGIS starten** und ein neues leeres Projekt anlegen (`Strg + N`).
2. **Koordinatenreferenzsystem (CRS) einstellen:**
   * Unten rechts auf den CRS-Button klicken (z. B. `EPSG:4326` oder `EPSG:3857`).
   * Für die Web-Darstellung: **`EPSG:3857` (WGS 84 / Pseudo-Mercator)** wählen.
   * Für amtliche metrische Österreich-Karten: **`EPSG:31287` (MGI / Austria Lambert)**.
3. **Hintergrundkarten hinzufügen (Browser-Panel links):**
   * **OpenStreetMap:** Unter `XYZ Tiles` ➔ Doppelklick auf `OpenStreetMap`.
   * **Österreichische basemap.at (Amtliche Luftbilder & Orthofotos):**
     * Rechtsklick auf `XYZ Tiles` ➔ *Neue Verbindung...*
     * **Name:** `basemap.at Orthofoto`
     * **URL:** `https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg`
     * Jetzt hast du 30cm-hochauflösende Luftbilder für ganz Österreich als Referenz!

---

## 3. CLMS-Rasterdaten laden (`data/raw/copernicus/`)

Ziehe die heruntergeladenen `.tif`-Dateien einfach per **Drag & Drop** aus dem Windows-Explorer in das QGIS-Kartenfenster:

```text
data/raw/copernicus/
├── imd_2018_donau_auen.tif   # Versiegelungsgrad (0–100 %)
├── waw_2018_donau_auen.tif   # Wasser & Feuchte (Klassen 0, 1, 2)
└── fty_2018_donau_auen.tif   # Waldtyp (0=kein Wald, 1=Laub, 2=Nadel)
```

QGIS erkennt die eingebettete Georeferenzierung automatisch und platziert die Raster exakt über dem Nationalpark Donau-Auen östlich von Wien.

---

## 4. Styling & Symbolisierung der CLMS-Layer

Standardmäßig stellt QGIS 1-Kanal-Raster als Graustufenbild dar. So stellst du die aussagekräftigen Fachfarben ein:

### A. IMD (Imperviousness Density — Versiegelung)
1. Rechtsklick auf den Layer `imd_...` ➔ **Eigenschaften** (`F7` für Layer-Gestaltungs-Panel).
2. Tab **Symbolisierung**:
   * **Symbolisierungstyp:** `Einkanalpseudofarbe` (*Singleband pseudocolor*)
   * **Farbverlauf:** `YlOrRd` (Gelb-Orange-Rot)
   * **Modus:** `Fortlaufend` oder `Gleiches Intervall` (Min: `0`, Max: `100`)
3. **Transparenz:**
   * Pixel mit Wert `0` (völlig unversiegelt) können transparent geschaltet werden:
     Tab *Transparenz* ➔ *Benutzerdefinierte Transparenzoptionen* ➔ `+` Wert `0` mit `100 %` Transparenz versehen.
   * *Ergebnis:* Straßen, Ortschaften und Wien leuchten rot/orange, die Auen bleiben frei.

### B. WAW (Water and Wetness — Gewässer & Feuchtgebiete)
1. Eigenschaften ➔ Tab **Symbolisierung**:
   * **Symbolisierungstyp:** `Palettierte/Eindeutige Werte` (*Paletted/Unique values*).
   * Klicke unten auf **Klassifizieren**.
2. Werte einfärben:
   * **0 (Trockenland):** Farbe transparent oder unscheinbares Hellgrau.
   * **1 (Feuchtgebiet / Röhricht):** Helles Türkis/Cyan (`#06B6D4`).
   * **2 (Offene Wasserflächen / Donau):** Kräftiges Dunkelblau (`#1D4ED8`).
3. *Ergebnis:* Die Donau und ihre Altarme stechen sofort plastisch hervor.

### C. FTY (Forest Type — Waldtyp)
1. Symbolisierungstyp: `Palettierte/Eindeutige Werte` ➔ *Klassifizieren*.
2. Werte einfärben:
   * **0 (Kein Wald):** Transparent.
   * **1 (Laubwald / Hartholz- & Weichholzaue):** Helles Laubgrün (`#22C55E`).
   * **2 (Nadelwald / Forste):** Dunkles Waldgrün (`#15803D`).
3. *Ergebnis:* Ideal zur schnellen Analyse der FFH-Auwald-Lebensraumtypen.

### D. TCD & GRA (Sprint 2b — Kronendichte & Grünland)
* **TCD (Tree Cover Density, 0–100 %):** `Einkanalpseudofarbe` mit Farbverlauf `Greens` oder `YlGn`.
* **GRA (Grassland, binär 0/1):** Palettiert: `0` transparent, `1` Wiesen-Hellgrün (`#84CC16`).

---

## 5. Nützliche Werkzeuge für die Analyse

* **Objekte abfragen (Identify Tool — `Strg + Umschalt + I`):**
  Klicke auf das blaue Information-Icon in der Symbolleiste und klicke auf einen beliebigen Punkt in der Karte. Das Panel zeigt dir sofort den exakten Pixelwert aller aktiven Raster (z. B. `IMD = 0%`, `WAW = 2 (Wasser)`, `FTY = 1 (Laubwald)`).
* **Deckkraft / Transparenz:**
  Im Layer-Gestaltungs-Panel kannst du den Schieberegler für **Deckkraft** (z. B. auf 60 %) stellen, um das Satelliten-Raster halbtransparent über das `basemap.at`-Luftbild zu legen.
* **Messwerkzeug (`M`):**
  Strecken oder Polygone abmessen, um Pufferbreiten der Altarme oder Distanzen zu Siedlungsrändern zu prüfen.

---

## 6. Ausblick: Was kommt in Sprint 3? (GeoParquet / GBIF)

In Sprint 3 erzeugen wir die Datei `data/processed/species_occurrences.parquet`.

* QGIS unterstützt **GeoParquet nativ** ab Version 3.28:
  * Du kannst die `.parquet`-Datei einfach wie ein Shapefile per Drag & Drop in QGIS ziehen!
  * Die Beobachtungspunkte von Feldhase (🐰), Neuntöter (🐦), Admiral (🦋) etc. erscheinen als Punkt-Layer direkt über deinen Copernicus-Rasterlayern.
  * Damit kannst du visuell sofort überprüfen, ob die räumliche Verschneidung (z. B. Hase auf Grünland, Neuntöter im Halboffenland) ökologisch plausibel ist.
