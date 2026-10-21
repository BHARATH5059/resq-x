from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.models.schemas import (
    EvacuationRoutingResult,
    RouteDetail,
    ZoneShelterRoute,
)
from app.simulation.risk_engine import apply_edge_risks_to_graph
from app.simulation.scenario import ScenarioState

# In-memory routing cache per scenario state configuration
_ROUTE_CACHE: Dict[Tuple[Any, ...], EvacuationRoutingResult] = {}


def clear_evacuation_cache() -> None:
    """Clear all cached routing results."""
    _ROUTE_CACHE.clear()


def get_routing_cache_key(state: ScenarioState) -> Tuple[Any, ...]:
    """Generate deterministic cache key for a ScenarioState."""
    return (
        id(state.graph),
        float(state.severity),
        frozenset(state.blocked_edges),
        frozenset(state.failed_bridges),
        frozenset(state.failed_shelters),
        tuple(sorted(z.id for z in state.zones)),
        tuple(sorted(s.id for s in state.shelters)),
    )


def path_to_geojson_linestring(
    graph: nx.DiGraph, path: List[int]
) -> Optional[Dict[str, Any]]:
    """
    Construct a GeoJSON LineString geometry ([lon, lat]) from a path of node IDs.
    Uses edge geometry if present, falling back to node coordinates.
    """
    if not path or len(path) < 2:
        if path:
            node = graph.nodes.get(path[0], {})
            return {
                "type": "LineString",
                "coordinates": [
                    [float(node.get("x", 0.0)), float(node.get("y", 0.0))]
                ],
            }
        return None

    coords: List[List[float]] = []
    for u, v in zip(path[:-1], path[1:]):
        edge_data = graph.get_edge_data(u, v, default={})
        geom = edge_data.get("geometry")

        if geom is not None and hasattr(geom, "coords"):
            edge_coords = [[float(x), float(y)] for x, y in geom.coords]
            if coords and edge_coords and coords[-1] == edge_coords[0]:
                coords.extend(edge_coords[1:])
            else:
                coords.extend(edge_coords)
        else:
            u_node = graph.nodes.get(u, {})
            v_node = graph.nodes.get(v, {})
            u_pt = [float(u_node.get("x", 0.0)), float(u_node.get("y", 0.0))]
            v_pt = [float(v_node.get("x", 0.0)), float(v_node.get("y", 0.0))]
            if not coords:
                coords.append(u_pt)
            coords.append(v_pt)

    return {
        "type": "LineString",
        "coordinates": coords,
    }


def compute_evacuation_routes(
    state: ScenarioState,
    config: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
) -> EvacuationRoutingResult:
    """
    Module 2: Evacuation Routing.
    - Annotates graph edges with edge risk and penalty costs.
    - Excludes impassable edges (edge_depth >= 1.0), manually blocked edges,
      and edges belonging to failed bridges.
    - Runs Dijkstra from each zone to each available shelter.
    - Computes both risk-aware route and plain shortest-path baseline route.
    - Returns structured routes with LineString GeoJSON ([lon, lat]).
    - If unreachable, returns status: "no_route" with cost inf (never crashes).
    - Caches results per scenario state.
    """
    cache_key = get_routing_cache_key(state)
    if use_cache and cache_key in _ROUTE_CACHE:
        return _ROUTE_CACHE[cache_key]

    # 1. Ensure edge risks are calculated and applied to graph for state.severity
    annotated_graph = apply_edge_risks_to_graph(
        graph=state.graph,
        flood_polygons=state.flood_polygons,
        severity=state.severity,
        config=config,
        inplace=True,
    )

    # 2. Gather excluded edge sets
    failed_bridge_edges: Set[Tuple[int, int]] = set()
    for bridge in state.bridges:
        if bridge.id in state.failed_bridges:
            for u, v in bridge.edges:
                failed_bridge_edges.add((int(u), int(v)))

    blocked_edges: Set[Tuple[int, int]] = set(
        (int(u), int(v)) for u, v in state.blocked_edges
    )

    # 3. Define filtering views
    def risk_edge_filter(u: int, v: int) -> bool:
        if (u, v) in blocked_edges or (u, v) in failed_bridge_edges:
            return False
        d = annotated_graph[u][v]
        if d.get("impassable", False) or d.get("edge_depth", 0.0) >= 1.0:
            return False
        return True

    def base_edge_filter(u: int, v: int) -> bool:
        if (u, v) in blocked_edges or (u, v) in failed_bridge_edges:
            return False
        return True

    risk_graph = nx.subgraph_view(annotated_graph, filter_edge=risk_edge_filter)
    base_graph = nx.subgraph_view(annotated_graph, filter_edge=base_edge_filter)

    # 4. Available shelters
    failed_shelter_ids = set(state.failed_shelters)

    routes_by_zone: Dict[str, Dict[str, ZoneShelterRoute]] = {}
    unreachable_count = 0
    differing_count = 0
    cut_off_zones: List[str] = []

    # Map zones for fast population lookup
    zone_dict = {z.id: z for z in state.zones}

    for zone in state.zones:
        z_id = zone.id
        z_node = zone.node
        routes_by_zone[z_id] = {}

        # Run single-source Dijkstra once per zone
        risk_costs: Dict[int, float] = {}
        risk_paths: Dict[int, List[int]] = {}
        if z_node in risk_graph:
            try:
                risk_costs, risk_paths = nx.single_source_dijkstra(
                    risk_graph, source=z_node, weight="edge_cost"
                )
            except Exception:
                risk_costs, risk_paths = {}, {}

        base_costs: Dict[int, float] = {}
        base_paths: Dict[int, List[int]] = {}
        if z_node in base_graph:
            try:
                base_costs, base_paths = nx.single_source_dijkstra(
                    base_graph, source=z_node, weight="length"
                )
            except Exception:
                base_costs, base_paths = {}, {}

        zone_has_any_route = False

        for shelter in state.shelters:
            s_id = shelter.id
            s_node = shelter.node

            # If shelter is failed, unreachable by definition
            is_shelter_failed = s_id in failed_shelter_ids

            # --- Risk Route ---
            if not is_shelter_failed and s_node in risk_paths:
                r_path = risk_paths[s_node]
                r_cost = float(risk_costs[s_node])
                r_len = float(
                    sum(
                        annotated_graph[u][v].get("length", 0.0)
                        for u, v in zip(r_path[:-1], r_path[1:])
                    )
                )
                r_status = "ok"
                r_geojson = path_to_geojson_linestring(annotated_graph, r_path)
                r_flooded = sum(
                    1
                    for u, v in zip(r_path[:-1], r_path[1:])
                    if annotated_graph[u][v].get("edge_depth", 0.0) > 0.0
                )
                r_max_depth = max(
                    [
                        annotated_graph[u][v].get("edge_depth", 0.0)
                        for u, v in zip(r_path[:-1], r_path[1:])
                    ],
                    default=0.0,
                )
                zone_has_any_route = True
            else:
                r_path = []
                r_cost = float("inf")
                r_len = float("inf")
                r_status = "no_route"
                r_geojson = None
                r_flooded = 0
                r_max_depth = 0.0
                unreachable_count += 1

            # --- Baseline Route (plain length) ---
            if not is_shelter_failed and s_node in base_paths:
                b_path = base_paths[s_node]
                b_cost = float(base_costs[s_node])
                b_len = b_cost
                b_status = "ok"
                b_geojson = path_to_geojson_linestring(annotated_graph, b_path)
                b_flooded = sum(
                    1
                    for u, v in zip(b_path[:-1], b_path[1:])
                    if annotated_graph[u][v].get("edge_depth", 0.0) > 0.0
                )
                b_max_depth = max(
                    [
                        annotated_graph[u][v].get("edge_depth", 0.0)
                        for u, v in zip(b_path[:-1], b_path[1:])
                    ],
                    default=0.0,
                )
            else:
                b_path = []
                b_cost = float("inf")
                b_len = float("inf")
                b_status = "no_route"
                b_geojson = None
                b_flooded = 0
                b_max_depth = 0.0

            baseline_detail = RouteDetail(
                status=b_status,
                cost=b_cost,
                length=b_len,
                path=b_path,
                route_geojson=b_geojson,
                flooded_edges_count=b_flooded,
                max_flood_depth=b_max_depth,
            )

            route = ZoneShelterRoute(
                zone_id=z_id,
                shelter_id=s_id,
                status=r_status,
                cost=r_cost,
                length=r_len,
                path=r_path,
                route_geojson=r_geojson,
                flooded_edges_count=r_flooded,
                max_flood_depth=r_max_depth,
                baseline_route=baseline_detail,
            )

            if r_status != b_status or r_path != b_path:
                differing_count += 1

            routes_by_zone[z_id][s_id] = route

        if not zone_has_any_route:
            cut_off_zones.append(z_id)

    # Compute unmet people for completely cut-off zones
    # (Affected people calculated by risk engine formula: round(population * depth_norm))
    total_unmet = 0
    for cz_id in cut_off_zones:
        z = zone_dict.get(cz_id)
        if z is not None:
            # Look up flood depth for zone
            from app.simulation.risk_engine import calculate_zone_risk

            max_pop = max((zn.population for zn in state.zones), default=1)
            z_risk = calculate_zone_risk(
                z, state.flood_polygons, max_pop, severity=state.severity
            )
            total_unmet += z_risk.affected_people

    result = EvacuationRoutingResult(
        severity=state.severity,
        routes=routes_by_zone,
        unreachable_pairs_count=unreachable_count,
        differing_routes_count=differing_count,
        cut_off_zones=cut_off_zones,
        total_unmet_people=total_unmet,
    )

    if use_cache:
        _ROUTE_CACHE[cache_key] = result

    return result
