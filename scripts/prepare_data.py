import os
import osmnx as ox

CENTER = (12.9815, 80.2209)   # (lat, lon) of demo area
DIST = 1200                   # metres; reduce if downloads keep timing out

SERVERS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

ox.settings.overpass_rate_limit = False   # skips the /status check that timed out
ox.settings.requests_timeout = 120
ox.settings.use_cache = True              # re-runs reuse downloaded responses

os.makedirs("data", exist_ok=True)

G = None
for url in SERVERS:
    try:
        ox.settings.overpass_url = url
        print("Trying", url)
        G = ox.graph_from_point(CENTER, dist=DIST, network_type="drive")
        break
    except Exception as e:
        print("Failed:", type(e).__name__)

if G is None:
    raise SystemExit("All servers failed. Try again later or from another network.")

ox.save_graphml(G, "data/road_graph.graphml")
print("Nodes:", len(G.nodes), "Edges:", len(G.edges))

try:
    tags = {"amenity": ["hospital", "clinic", "school", "fire_station"]}
    fac = ox.features_from_point(CENTER, tags, dist=DIST)
    cols = [c for c in ["amenity", "name", "geometry"] if c in fac.columns]
    fac[cols].to_file("data/facilities.geojson", driver="GeoJSON")
    print("Facilities:", len(fac))
except Exception as e:
    print("Facilities download failed:", type(e).__name__, "- retry later")