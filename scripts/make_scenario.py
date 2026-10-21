import csv
import json
import math
import os

import networkx as nx
import osmnx as ox

G = ox.load_graphml("data/road_graph.graphml")
nodes = [(n, float(d["y"]), float(d["x"])) for n, d in G.nodes(data=True)]


def nearest(lat, lon):
    """Nearest graph node to a point, using plain math (no extra packages)."""
    best = None
    for n, y, x in nodes:
        dy = (y - lat) * 111320
        dx = (x - lon) * 111320 * math.cos(math.radians(lat))
        d = math.hypot(dx, dy)
        if best is None or d < best[1]:
            best = (n, d)
    return best


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def with_node(items):
    out = []
    for it in items:
        n, dist = nearest(it["lat"], it["lon"])
        row = dict(it)
        row["node"] = n
        row["snap_m"] = round(dist)
        out.append(row)
        if dist > 150:
            print(f'WARNING: {it["name"]} is {dist:.0f} m from the nearest road node')
    return out


# ---------- shelters (real school locations, SIMULATED capacity) ----------
shelters = with_node([
    {"id": "S1", "name": "Government Higher Secondary School, Velachery", "lat": 12.98799, "lon": 80.21986, "capacity": 1000},
    {"id": "S2", "name": "Chennai Higher Secondary School", "lat": 12.98522, "lon": 80.21895, "capacity": 800},
    {"id": "S3", "name": "Guru Nanak School", "lat": 12.99067, "lon": 80.22089, "capacity": 900},
    {"id": "S4", "name": "SAN Academy", "lat": 12.97579, "lon": 80.21239, "capacity": 700},
    {"id": "S5", "name": "St. Savio Matriculation Higher Secondary School", "lat": 12.98174, "lon": 80.22619, "capacity": 500},
    {"id": "S6", "name": "Sri Chaitanya Techno School", "lat": 12.97756, "lon": 80.21791, "capacity": 700},
])
write_csv("data/shelters.csv", shelters)

# ---------- hospitals (real locations, SIMULATED capacity) ----------
hospitals = with_node([
    {"id": "H1", "name": "Velachery SABA Hospital", "lat": 12.98627, "lon": 80.22989, "beds_available": 40},
    {"id": "H2", "name": "Helios Hospital", "lat": 12.98559, "lon": 80.21891, "beds_available": 30},
    {"id": "H3", "name": "Appasamy Krishna Hospital", "lat": 12.97586, "lon": 80.22050, "beds_available": 50},
    {"id": "H4", "name": "Athipathi Hospital", "lat": 12.97627, "lon": 80.22220, "beds_available": 25},
])
write_csv("data/hospitals.csv", hospitals)

# ---------- population zones (INVENTED) ----------
zones = with_node([
    {"id": "P1", "name": "South-East Colony", "lat": 12.9745, "lon": 80.2265, "population": 2400, "vulnerable_share": 0.22},
    {"id": "P2", "name": "Central Residential", "lat": 12.9810, "lon": 80.2180, "population": 3200, "vulnerable_share": 0.18},
    {"id": "P3", "name": "North Canal Settlement", "lat": 12.9885, "lon": 80.2135, "population": 1800, "vulnerable_share": 0.30},
    {"id": "P4", "name": "East Apartments", "lat": 12.9850, "lon": 80.2285, "population": 2100, "vulnerable_share": 0.15},
    {"id": "P5", "name": "West Layout", "lat": 12.9770, "lon": 80.2120, "population": 1500, "vulnerable_share": 0.20},
    {"id": "P6", "name": "North-East Market Area", "lat": 12.9900, "lon": 80.2215, "population": 1200, "vulnerable_share": 0.12},
])
write_csv("data/population_zones.csv", zones)

# ---------- rescue base (fire station) and resources ----------
base_node, base_dist = nearest(12.97685, 80.22763)
resources = {
    "base": {"name": "Fire station (rescue base)", "lat": 12.97685, "lon": 80.22763, "node": base_node},
    "rescue_teams": 3,
    "ambulances": 2,
    "boats": 2,
    "food_packets": 500,
    "medical_kits": 100,
}
with open("data/resources.json", "w", encoding="utf-8") as f:
    json.dump(resources, f, indent=2)


# ---------- flood zones (INVENTED polygons) ----------
def box(lat0, lon0, lat1, lon1):
    return [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]


flood_defs = [
    ("F1", "Low-lying south-east", 12.972, 80.222, 12.978, 80.231, 0.9),
    ("F2", "Central basin", 12.978, 80.214, 12.984, 80.222, 0.8),
    ("F3", "North canal belt", 12.985, 80.210, 12.991, 80.218, 0.5),
    ("F4", "East pocket", 12.982, 80.226, 12.988, 80.231, 0.3),
]
flood = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"id": i, "name": n, "depth_m": d, "simulated": True},
            "geometry": {"type": "Polygon", "coordinates": box(a, b, c, e)},
        }
        for i, n, a, b, c, e, d in flood_defs
    ],
}
with open("data/flood_zones.geojson", "w", encoding="utf-8") as f:
    json.dump(flood, f, indent=2)

# ---------- critical crossings for the failure demo (SIMULATED) ----------
bridge_defs = [
    {"id": "B1", "name": "Velachery Bypass Road crossing (simulated)", "edge": (325207488, 4265654365)},
    {"id": "B2", "name": "Major Mukund Varadharajan Salai crossing (simulated)", "edge": (338406860, 12497489527)},
    {"id": "B3", "name": "Vijayanagar 1st Main Road crossing (simulated)", "edge": (2167148944, 299883943)},
]
bridges = []
for b in bridge_defs:
    u, v = b["edge"]
    edges = []
    for a, c in ((u, v), (v, u)):          # include the reverse direction only if it exists
        if G.has_edge(a, c):
            edges.append([a, c])
    if not edges:
        print(f'WARNING: no edge found for {b["id"]}')
    bridges.append({"id": b["id"], "name": b["name"], "edges": edges})
with open("data/bridges.json", "w", encoding="utf-8") as f:
    json.dump(bridges, f, indent=2)

# ---------- sanity check: is the road network connected? ----------
scc = max(nx.strongly_connected_components(G), key=len)
print(f"Graph: {len(G.nodes)} nodes, largest connected part: {len(scc)} ({len(scc) / len(G.nodes):.0%})")
for name, items in [("shelters", shelters), ("hospitals", hospitals), ("zones", zones)]:
    outside = [i["name"] for i in items if str(i["node"]) not in {str(n) for n in scc}]
    print(f"{name}: {len(items)} written, not in connected network: {outside or 'none'}")
print("Done. Files written to data/")