import osmnx as ox
import geopandas as gpd

G = ox.load_graphml("data/road_graph.graphml")
fac = gpd.read_file("data/facilities.geojson")

print("Facilities by type:")
print(fac["amenity"].value_counts(), "\n")

print("Named facilities:")
named = fac[fac["name"].notna()] if "name" in fac.columns else fac
for _, r in named.iterrows():
    p = r.geometry.centroid
    print(f'{r["amenity"]:12} {str(r.get("name", "")):40} lat={p.y:.5f} lon={p.x:.5f}')

bridges = [(u, v, d.get("name", "")) for u, v, d in G.edges(data=True)
           if str(d.get("bridge", "")).lower() in ("yes", "true", "viaduct", "movable")]
print("\nBridge edges:", len(bridges))
for b in bridges[:15]:
    print(b)