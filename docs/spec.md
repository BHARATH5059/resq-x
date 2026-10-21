# RESQ-X Specification (Modules 1-4)

Course prototype: disaster response simulator for a flood scenario in Velachery, Chennai.
All hazard, population, capacity and resource numbers are SIMULATED. The UI must show a visible "SIMULATED DATA" badge. This is not an operational dispatch system.

Module 5 (scam and fake-donation detector) is out of scope for now. Do not build it yet.

## 1. Stack and rules

- Backend: Python 3.14, FastAPI, Pydantic, NetworkX, OSMnx (loading only), OR-Tools, Shapely, pandas, pytest.
- Frontend: React + TypeScript + Vite + Leaflet (built later, after the backend tests pass).
- No database. All data is read from files in `data/` at startup and held in memory.
- Do NOT modify any file in `data/`. Do NOT re-download map data.
- Write tests first or together with each module. A module is done only when its tests pass (`pytest`).
- Build one module at a time, in the order below. Stop and report after each module.
- Coordinates: GeoJSON uses [lon, lat]. Leaflet uses [lat, lon]. Backend JSON sends GeoJSON.

## 2. Data files (already created, read-only)

| File | Contents |
|---|---|
| `data/road_graph.graphml` | Road network, 1266 nodes, 3073 edges. Load with `ox.load_graphml`. Edges have `length` (metres). Node ids load as integers. |
| `data/facilities.geojson` | Real hospitals, clinics, schools, fire station (for map display only) |
| `data/shelters.csv` | id, name, lat, lon, capacity, node, snap_m (6 shelters, simulated capacity) |
| `data/hospitals.csv` | id, name, lat, lon, beds_available, node, snap_m (4 hospitals) |
| `data/population_zones.csv` | id, name, lat, lon, population, vulnerable_share, node, snap_m (6 zones) |
| `data/resources.json` | base (fire station, with node), rescue_teams, ambulances, boats, food_packets, medical_kits |
| `data/flood_zones.geojson` | 4 polygons, property `depth_m` (0.3 to 1.2) |
| `data/bridges.json` | id, name, edges ([u, v] pairs) for B1, B2, B3 |

Graph handling: convert the MultiDiGraph to a DiGraph, keeping the shortest `length` edge for each (u, v). Keep the bridge edges.

## 3. Core state: `ScenarioState`

Holds: graph, zones, shelters, hospitals, resources, flood polygons, `severity` (float, default 1.0), `blocked_edges` (set of (u, v)), `failed_shelters`, `failed_hospitals`, `failed_bridges`, and `baseline` (the plan produced by the last `/simulate`). Every module reads this one object. Failures are cumulative until `/reset`.

## 4. Module 1: Risk engine (`risk_engine.py`)

For each population zone:

- `depth` = maximum `depth_m` among flood polygons that contain the zone centre point, multiplied by `severity`. If none contain it, 0.
- `depth_norm = min(depth / 1.5, 1.0)`
- `pop_norm = population / max(population over all zones)`
- `risk_score = 0.5 * depth_norm + 0.3 * vulnerable_share_norm + 0.2 * pop_norm`, where `vulnerable_share_norm = min(vulnerable_share / 0.35, 1.0)`
- `risk_level`: below 0.25 low, below 0.5 medium, below 0.75 high, otherwise critical.
- `affected_people = round(population * depth_norm)`
- `priority = risk_score * affected_people`

Weights and thresholds go in a config dict at the top of the file, not hard-coded inside functions.

Edge risk: for each road edge, take its midpoint (or sample points along its geometry if present). `edge_depth` = depth of the deepest flood polygon containing it, times `severity`.

- `edge_depth >= 1.0`: edge is impassable.
- Otherwise `edge_cost = length * (1 + 5 * min(edge_depth / 1.0, 1.0))`.

## 5. Module 2: Evacuation routing (`evacuation.py`)

- Build a weighted graph using `edge_cost`. Exclude impassable edges, manually blocked edges, and edges of failed bridges.
- For each zone, run Dijkstra from the zone node and record the cost and path to every available shelter. Unreachable shelters get cost infinity.
- Cache results per scenario state. Do not recompute inside loops.
- Return `route_geojson` for each assigned route (LineString, [lon, lat]).
- Also compute a baseline route using plain `length` with no risk penalty, for comparison.
- If no shelter is reachable from a zone, return `status: "no_route"` and count its people as unmet. Never crash.

## 6. Module 3: Resource and shelter allocator (`resource_optimizer.py`)

Use OR-Tools.

**Shelter assignment.** Decision: how many people from each zone go to each available (not failed) shelter. Constraints: sum over shelters for a zone is at most `affected_people`; sum over zones for a shelter is at most its capacity; only reachable pairs are allowed. Objective: assign as many people as possible, then minimise total travel cost. `unmet_people = affected_people - assigned`. Integer variables (min-cost flow or CP-SAT).

**Rescue teams.** Each team goes to at most one zone and each zone gets at most one team. Zones must be reachable from the base node. Maximise total `priority` of served zones, with a small penalty for travel cost. Zones with no team are reported as unserved.

**Ambulances.** Same rule, plus each ambulance is paired with the nearest reachable non-failed hospital that has beds available.

**Supplies.** Distribute `food_packets` in proportion to `affected_people`, and `medical_kits` in proportion to `affected_people * vulnerable_share`, among zones reachable from the base. Use largest-remainder rounding so the totals match exactly. Unreachable zones get 0 and are reported as unmet.

Every output must include unmet demand. Never ignore it silently.

## 7. Module 4: Failure simulator and comparison (`failure_simulator.py`)

Failure events:

| type | id | effect |
|---|---|---|
| `block_bridge` | B1, B2, B3 | removes the bridge edges |
| `block_edge` | [u, v] | removes one edge |
| `fail_shelter` | S1..S6 | shelter unavailable |
| `fill_shelter` | S1..S6 | shelter capacity set to 0 |
| `fail_hospital` | H1..H4 | hospital unavailable |
| `reduce_resources` | field and amount | for example rescue_teams 3 -> 1 |

After an event, recompute modules 1-3 and return a diff against `state.baseline`:

- For each zone: route changed (bool), old and new route length, old and new assigned shelter, unmet before and after.
- Totals: people assigned before and after, unmet before and after, total travel cost before and after.
- Resource movements: which team, ambulance and supply assignments changed.
- A short list of plain-language change messages, generated from the diff (rule-based text, no LLM).

## 8. API (`api/routes.py`)

| Method and path | Body | Returns |
|---|---|---|
| GET `/scenario` | none | static map data: zones, shelters, hospitals, bridges, flood polygons, base (GeoJSON) |
| POST `/simulate` | `{severity: 1.0, resources: {optional overrides}}` | `{risk, routes, allocation, unmet, totals}`, and saves it as the baseline |
| POST `/failure` | `{type, id, amount?}` | `{plan, diff}` |
| POST `/reset` | none | clears failures, returns to the baseline scenario |
| GET `/health` | none | `{status: "ok"}` |

Enable CORS for `http://localhost:5173`. Use Pydantic models for every request and response. Validate ids and return 404 or 422 with a clear message for unknown ids.

## 9. Folder layout (backend)

```
backend/app/main.py
backend/app/api/routes.py
backend/app/models/schemas.py
backend/app/simulation/scenario.py
backend/app/simulation/risk_engine.py
backend/app/simulation/evacuation.py
backend/app/simulation/resource_optimizer.py
backend/app/simulation/failure_simulator.py
backend/tests/
```

## 10. Required tests

Create a tiny hand-made graph fixture (about 6 nodes, 2 shelters, 1 bridge) where the correct answers are known, and test against it, not only the real graph.

1. Higher severity gives higher risk scores and more affected people.
2. A zone outside every flood polygon has depth 0 and no affected people.
3. Blocking the bridge removes every route that used it, and the new route avoids it.
4. If no path exists, the zone is reported as `no_route` and its people counted as unmet. No exception.
5. Total people assigned to a shelter never exceed its capacity.
6. Filling or failing a shelter reassigns people to other shelters, or reports them as unmet.
7. Reducing rescue teams from 3 to 1 leaves only one zone served and the others reported as unserved.
8. Increasing risk in one zone raises its priority and its team assignment order.
9. Supply totals equal the inputs exactly (food packets and medical kits).
10. `/simulate` then `/failure` returns a diff where changed fields differ from the baseline.
11. Baseline comparison: risk-aware routing avoids at least one flooded edge that plain shortest-path uses (test on the real graph, report the numbers).

## 11. Definition of done for the backend

- All tests pass with `pytest`.
- `http://localhost:8000/docs` shows all endpoints and they work.
- The demo sequence works: `/simulate` then block B1 then fill S1 then compare, with sensible output.
- A short `docs/methodology.md` lists the formulas, assumptions and limitations in plain language.

## 12. Frontend (later, do not start until the backend is done)

Dashboard from the Stitch design: left controls (severity slider, block bridge, fail or fill shelter, reduce resources, Run, Reset), centre Leaflet map (flood zones, roads, shelters, hospitals, routes, blocked edges in red), right tabs (Risk, Routes, Resources, Comparison). Show the SIMULATED DATA badge at all times.
