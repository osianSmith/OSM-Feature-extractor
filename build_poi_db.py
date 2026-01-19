#!/usr/bin/env python3

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

# ================================
# CONFIG
# ================================

OSMIUM = "osmium"

BASE_DIR = Path(__file__).parent
REGIONS_DIR = BASE_DIR / "regions"
OUTPUT_DIR = BASE_DIR / "output"
TAG_FILE = BASE_DIR / "poi-tags.txt"

OUTPUT_DIR.mkdir(exist_ok=True)

# ================================
# HELPERS
# ================================

def run(cmd):
    print("▶", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)

def load_tags():
    with open(TAG_FILE) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]

def centroid_from_geom(geom):
    """Simple centroid for Polygon / MultiPolygon"""
    if geom["type"] == "Polygon":
        rings = [geom["coordinates"][0]]
    else:  # MultiPolygon
        rings = [poly[0] for poly in geom["coordinates"]]

    lats, lons = [], []
    for ring in rings:
        for lon, lat in ring:
            lons.append(lon)
            lats.append(lat)

    return sum(lons) / len(lons), sum(lats) / len(lats)

# ================================
# CLASSIFICATION
# ================================

def classify(props):
    # ---- Places ----
    place = props.get("place")
    if place == "city": return (100, "city")
    if place == "town": return (101, "town")
    if place == "village": return (102, "village")
    if place == "hamlet": return (103, "hamlet")
    if place == "suburb": return (104, "suburb")

    # ---- Historic ----
    if props.get("historic") == "castle": return (1, "castle")
    if props.get("historic") in ("abbey", "monastery"): return (2, "abbey")
    if props.get("historic"): return (7, props["historic"])

    # ---- Religion ----
    if props.get("amenity") == "place_of_worship":
        return (3, props.get("religion", "worship"))

    # ---- Food & Drink ----
    if props.get("amenity") == "cafe": return (10, "cafe")
    if props.get("amenity") == "pub": return (11, "pub")
    if props.get("amenity") == "restaurant": return (12, "restaurant")
    if props.get("amenity") == "fast_food": return (13, "fast_food")
    if props.get("amenity") == "bar": return (14, "bar")

    # ---- Shops ----
    if props.get("shop"):
        return (20, props["shop"])

    # ---- Tourism ----
    if props.get("tourism") in ("attraction", "museum", "viewpoint"):
        return (30, props["tourism"])

    # ---- Leisure ----
    if props.get("leisure"):
        return (40, props["leisure"])

    # ---- Nature ----
    if props.get("natural") == "peak": return (50, "peak")
    if props.get("man_made") == "survey_point": return (51, "trig_point")

    return None

def classify_geo(props):
    if props.get("place") == "island":
        return "island"
    if props.get("natural") == "peak":
        return "peak"
    return None

# ================================
# SQLITE SCHEMA
# ================================

SCHEMA_SQL = """
DROP TABLE IF EXISTS pois;
DROP TABLE IF EXISTS poi_index;
DROP TABLE IF EXISTS geo_features;
DROP TABLE IF EXISTS geo_index;

CREATE TABLE pois (
    id INTEGER PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    type INTEGER NOT NULL,
    name TEXT NOT NULL,
    subtype TEXT,
    tags TEXT
);

CREATE VIRTUAL TABLE poi_index USING rtree(
    id,
    minLat, maxLat,
    minLon, maxLon
);

CREATE TABLE geo_features (
    id INTEGER PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    kind TEXT NOT NULL,
    name TEXT,
    tags TEXT
);

CREATE VIRTUAL TABLE geo_index USING rtree(
    id,
    minLat, maxLat,
    minLon, maxLon
);
"""

# ================================
# BUILD ONE REGION
# ================================

def build_region(pbf_file: Path):
    region_name = pbf_file.stem.replace("-latest", "")
    print(f"\n=== BUILDING {region_name.upper()} ===\n")

    filtered_pbf = BASE_DIR / f"{region_name}-filtered.osm.pbf"
    geojson = BASE_DIR / f"{region_name}.geojson"
    sqlite_db = OUTPUT_DIR / f"{region_name}.sqlite"

    tags = load_tags()

    run([
        OSMIUM, "tags-filter",
        str(pbf_file),
        "--overwrite",
        f"--output={filtered_pbf}",
        *tags
    ])

    run([
        OSMIUM, "export",
        str(filtered_pbf),
        "--overwrite",
        "-o", str(geojson)
    ])

    db = sqlite3.connect(sqlite_db)
    cur = db.cursor()
    cur.executescript(SCHEMA_SQL)

    with open(geojson, "r") as f:
        data = json.load(f)

    imported = 0

    for feat in data["features"]:
        geom = feat.get("geometry")
        props = feat.get("properties", {})
        geom_type = geom.get("type")

        if geom_type == "Point":
            lon, lat = geom["coordinates"]
        elif geom_type in ("Polygon", "MultiPolygon"):
            lon, lat = centroid_from_geom(geom)
        else:
            continue

        osm_id = props.get("id")

        # ---- Geographic features first ----
        geo_kind = classify_geo(props)
        if geo_kind:
            # ---- geo_features table (metadata) ----
            cur.execute(
                "INSERT OR IGNORE INTO geo_features VALUES (?,?,?,?,?,?)",
                (
                    osm_id,
                    lat,
                    lon,
                    geo_kind,
                    props.get("name"),
                    json.dumps(props)
                )
            )

            # ---- geo_index table (spatial index) ----
            cur.execute(
                "INSERT OR IGNORE INTO geo_index VALUES (?,?,?,?,?)",
                (osm_id, lat, lat, lon, lon)
            )
            continue


        # ---- POIs ----
        name = props.get("name")
        if not name and props.get("historic") in (
            "standing_stone", "megalith", "stone"
        ):
            name = props["historic"].replace("_", " ").title()

        if not name:
            continue

        classification = classify(props)
        if not classification:
            continue

        poi_type, subtype = classification

        cur.execute(
            "INSERT OR IGNORE INTO pois VALUES (?,?,?,?,?,?,?)",
            (osm_id, lat, lon, poi_type, name, subtype, json.dumps(props))
        )

        cur.execute(
            "INSERT OR IGNORE INTO poi_index VALUES (?,?,?,?,?)",
            (osm_id, lat, lat, lon, lon)
        )

        imported += 1
        if imported % 100_000 == 0:
            print(f"  Imported {imported:,}")

    db.commit()
    db.close()

    filtered_pbf.unlink(missing_ok=True)
    geojson.unlink(missing_ok=True)

    print(f"\n✔ {region_name}: {imported:,} POIs imported")
    print(f"📦 Output DB: {sqlite_db}\n")

# ================================
# MAIN
# ================================

def main():
    pbf_files = sorted(REGIONS_DIR.glob("*.osm.pbf"))
    if not pbf_files:
        print("❌ No .osm.pbf files found")
        sys.exit(1)

    for pbf in pbf_files:
        build_region(pbf)

    print("=== ALL REGIONS COMPLETE ===")

if __name__ == "__main__":
    main()
