import sys

packages = [
    ("pystac_client", "pystac_client"),
    ("rasterio", "rasterio"),
    ("geopandas", "geopandas"),
    ("pygbif", "pygbif"),
    ("duckdb", "duckdb"),
    ("fastapi", "fastapi"),
    ("folium", "folium"),
    ("rioxarray", "rioxarray"),
    ("shapely", "shapely"),
    ("pyproj", "pyproj"),
]

all_ok = True
for import_name, display in packages:
    try:
        mod = __import__(import_name)
        ver = getattr(mod, "__version__", "ok")
        print(f"  OK {display} {ver}")
    except ImportError as e:
        print(f"  FAIL {display}: {e}")
        all_ok = False

# Eigenes Paket testen
try:
    from biodiv_horizon.config import TEST_AREA_NAME, LEITARTEN
    print(f"  OK biodiv_horizon (Testgebiet: {TEST_AREA_NAME})")
    print(f"  OK Leitarten: {[v['common_name_de'] for v in LEITARTEN.values()]}")
except Exception as e:
    print(f"  FAIL biodiv_horizon: {e}")
    all_ok = False

print()
print("ALLE OK" if all_ok else "FEHLER GEFUNDEN")
sys.exit(0 if all_ok else 1)
