Here’s a padded-out, production-ready **GitHub README** you can drop straight into the repo. I’ve expanded setup, data sources, workflow, and outputs while keeping it honest to how the script actually works.

# OSM Feature Extractor

**OSM Feature Extractor** is a lightweight Python tool that extracts useful Points of Interest (POIs) and geographic features from OpenStreetMap `.osm.pbf` files and converts them into fast, queryable **SQLite databases with spatial indexes**.

It is designed for apps that *consume* POI data (search, discovery, proximity queries) rather than perform full navigation or routing.

---

## Why this exists

OpenStreetMap datasets are **huge** and contain far more information than many applications need. Filtering OSM data at runtime is:

* CPU and memory intensive
* Poor practice for production systems
* Slow on mobile and embedded platforms

This tool moves that cost **offline**, producing compact SQLite databases optimised for spatial lookups.

---

## Key Features

* ✅ Reads **multiple `.osm.pbf` files** (useful for regions or countries)
* ✅ Whitelists tags using a simple `poi-tags.txt` file
* ✅ Supports **Points, Polygons, and MultiPolygons**
* ✅ Generates **SQLite databases with R-Tree spatial indexes**
* ✅ Classifies POIs into numeric types + human-readable subtypes
* ✅ Separates **POIs** from **geographic features** (islands, peaks, etc.)
* ✅ Uses industry-standard **osmium** tooling

---

## Typical Use Cases

* Mobile or desktop apps showing nearby POIs
* Offline maps or discovery apps
* Data pipelines that need clean POI datasets
* Reducing OSM data size for embedded systems
* Pre-processing OSM data for search indexes

---

## Project Structure

```text
.
├── regions/
│   └── england-latest.osm.pbf
├── output/
│   └── england.sqlite
├── poi-tags.txt
├── extract.py
└── README.md
```

---

## Requirements

### System Dependencies

You **must** have `osmium` installed:

```bash
brew install osmium        # macOS
sudo apt install osmium-tool  # Debian / Ubuntu
```

### Python

* Python **3.9+**
* Uses only standard library modules

---

## Getting OSM Data

Download `.osm.pbf` files from **Geofabrik**:

[https://download.geofabrik.de/](https://download.geofabrik.de/)

Examples:

```text
europe/great-britain/england-latest.osm.pbf
europe/ireland-and-northern-ireland-latest.osm.pbf
```

Place one or more `.osm.pbf` files into the `regions/` directory.

---

## Tag Whitelisting (`poi-tags.txt`)

This file controls **what data is extracted**.

Each line is passed directly to `osmium tags-filter`.

Example:

```text
amenity=*
shop=*
tourism=*
historic=*
leisure=*
place=*
natural=*
man_made=*
```

Comments are supported:

```text
# Food & drink
amenity=cafe
amenity=restaurant
amenity=pub
```

---

## Running the Extractor

From the project root:

```bash
python3 extract.py
```

The tool will:

1. Filter each `.osm.pbf` using `poi-tags.txt`
2. Export filtered data to GeoJSON
3. Convert features into SQLite
4. Build spatial R-tree indexes
5. Clean up intermediate files

---

## Output

For each input region you get:

```text
output/
└── england.sqlite
```

### Database Schema

#### POIs

```sql
pois
├── id        INTEGER (OSM ID)
├── lat       REAL
├── lon       REAL
├── type      INTEGER
├── name      TEXT
├── subtype   TEXT
├── tags      JSON
```

#### Spatial Index

```sql
poi_index (R-Tree)
```

#### Geographic Features

Used for things like islands and peaks:

```sql
geo_features
geo_index (R-Tree)
```

---

## Classification System

POIs are classified into numeric `type` values with readable `subtype`s.

Examples:

| Type | Category               |
| ---: | ---------------------- |
|    1 | Castle                 |
|   10 | Cafe                   |
|   11 | Pub                    |
|   12 | Restaurant             |
|  20+ | Shops                  |
|  30+ | Tourism                |
|  40+ | Leisure                |
| 100+ | Places (towns, cities) |

This makes filtering fast and predictable in downstream apps.

---

## Geometry Handling

* **Points** → used directly
* **Polygons / MultiPolygons** → converted to centroids
* Unsupported geometries are skipped

This keeps the output lightweight and app-friendly.

---

## Query Example

Find POIs within a bounding box:

```sql
SELECT p.*
FROM pois p
JOIN poi_index i ON p.id = i.id
WHERE i.minLat >= ?
  AND i.maxLat <= ?
  AND i.minLon >= ?
  AND i.maxLon <= ?;
```

---

## Performance Notes

* Imports ~100k POIs per region efficiently
* Uses `INSERT OR IGNORE` to avoid duplicates
* R-Tree indexes give near-instant spatial queries
* Intermediate files are automatically cleaned up

---

## Limitations

* Not intended for routing or navigation
* Geometry is simplified to centroids
* Classification rules are opinionated (easy to extend)

---

## Future Ideas

* Region merging
* Custom classification configs
* PostGIS output
* Incremental updates
* Vector tile export

---

## License

MIT License – use it however you like 👍

---
