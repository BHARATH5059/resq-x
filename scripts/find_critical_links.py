import sys
from collections import Counter

sys.path.insert(0, "backend")
from app.simulation.scenario import load_scenario_state
from app.simulation.evacuation import compute_evacuation_routes

state = load_scenario_state("data")
state.severity = 1.0
base = compute_evacuation_routes(state, use_cache=False)

use = Counter()
for zid, row in base.routes.items():
    for sid, r in row.items():
        if r.path and len(r.path) > 1:
            for e in zip(r.path[:-1], r.path[1:]):
                use[e] += 1

print("Top 15 most-used road edges at severity 1.0")
print("(edge, pairs using it, pairs changed when blocked, zones cut off, length m, street name)\n")

rows = []
for (u, v), n in use.most_common(15):
    st = state.copy()
    st.blocked_edges.add((u, v))
    if state.graph.has_edge(v, u):
        st.blocked_edges.add((v, u))
    new = compute_evacuation_routes(st, use_cache=False)
    changed = sum(
        1
        for zid, row in base.routes.items()
        for sid, r in row.items()
        if new.routes[zid][sid].path != r.path
    )
    data = state.graph[u][v]
    ux, uy = state.graph.nodes[u]["x"], state.graph.nodes[u]["y"]
    print(
        f"({u}, {v}) used={n} changed={changed} cut_off={new.cut_off_zones} "
        f"len={float(data.get('length', 0)):.0f}m name={data.get('name', '')!r} lat={uy:.5f} lon={ux:.5f}"
    )