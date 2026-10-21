from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import networkx as nx
from shapely.geometry import Point

from app.models.schemas import EdgeRisk, RiskAssessmentResult, Zone, ZoneRisk
from app.simulation.scenario import FloodPolygon, ScenarioState

# Weights, thresholds, and normalization factors for Module 1 (Risk Engine).
# Configurable at the module level or via overrides.
DEFAULT_RISK_CONFIG: Dict[str, Any] = {
    # Normalization bounds
    "depth_norm_max": 1.5,
    "vulnerable_share_norm_max": 0.35,
    # Risk score component weights (sum to 1.0)
    "weight_depth": 0.5,
    "weight_vulnerable": 0.3,
    "weight_population": 0.2,
    # Categorical risk level classification: (exclusive_upper_bound, level_label)
    "risk_level_thresholds": [
        (0.25, "low"),
        (0.50, "medium"),
        (0.75, "high"),
        (float("inf"), "critical"),
    ],
    # Edge risk thresholds and cost penalties
    "edge_impassable_depth": 1.0,
    "edge_penalty_multiplier": 5.0,
    "edge_depth_norm_max": 1.0,
    # Edge geometry sampling: default to midpoint (0.5)
    "edge_sample_fractions": [0.5],
}


def classify_risk_level(
    risk_score: float, config: Optional[Dict[str, Any]] = None
) -> str:
    """Classify numeric risk score into low, medium, high, or critical."""
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}
    thresholds: List[Tuple[float, str]] = cfg["risk_level_thresholds"]
    for upper_bound, label in thresholds:
        if risk_score < upper_bound:
            return label
    return "critical"


def calculate_zone_risk(
    zone: Union[Zone, Dict[str, Any]],
    flood_polygons: Sequence[FloodPolygon],
    max_population: float,
    severity: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
) -> ZoneRisk:
    """
    Compute risk assessment for a single population zone.
    Formulas from RESQ-X spec:
    - depth = max depth_m among flood polygons containing zone centre point * severity (0 if none)
    - depth_norm = min(depth / 1.5, 1.0)
    - pop_norm = population / max(population over all zones)
    - vulnerable_share_norm = min(vulnerable_share / 0.35, 1.0)
    - risk_score = 0.5 * depth_norm + 0.3 * vulnerable_share_norm + 0.2 * pop_norm
    - risk_level: below 0.25 low, below 0.5 medium, below 0.75 high, otherwise critical
    - affected_people = round(population * depth_norm)
    - priority = risk_score * affected_people
    """
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}

    # Extract zone attributes safely
    zone_id = str(zone.get("id") if hasattr(zone, "get") else zone["id"])
    name = str(zone.get("name") if hasattr(zone, "get") else zone["name"])
    lat = float(zone.get("lat") if hasattr(zone, "get") else zone["lat"])
    lon = float(zone.get("lon") if hasattr(zone, "get") else zone["lon"])
    pop = int(zone.get("population") if hasattr(zone, "get") else zone["population"])
    vuln = float(
        zone.get("vulnerable_share")
        if hasattr(zone, "get")
        else zone["vulnerable_share"]
    )
    node = int(zone.get("node") if hasattr(zone, "get") else zone["node"])

    # Zone centre point in GeoJSON coordinates [lon, lat] -> Point(lon, lat)
    pt = Point(lon, lat)

    # Depth: max depth_m among flood polygons that contain the zone centre, times severity
    matching_depths = [
        poly.depth_m for poly in flood_polygons if poly.contains_point(pt)
    ]
    max_polygon_depth = max(matching_depths, default=0.0)
    depth = max(0.0, max_polygon_depth * severity)

    # Normalizations
    depth_norm_max = float(cfg["depth_norm_max"])
    depth_norm = min(depth / depth_norm_max, 1.0) if depth_norm_max > 0 else 0.0

    pop_norm = (pop / max_population) if max_population > 0 else 0.0

    vuln_norm_max = float(cfg["vulnerable_share_norm_max"])
    vulnerable_share_norm = (
        min(vuln / vuln_norm_max, 1.0) if vuln_norm_max > 0 else 0.0
    )

    # Risk score
    w_depth = float(cfg["weight_depth"])
    w_vuln = float(cfg["weight_vulnerable"])
    w_pop = float(cfg["weight_population"])
    risk_score = (
        w_depth * depth_norm
        + w_vuln * vulnerable_share_norm
        + w_pop * pop_norm
    )

    risk_level = classify_risk_level(risk_score, cfg)
    affected_people = int(round(pop * depth_norm))
    priority = float(risk_score * affected_people)

    return ZoneRisk(
        zone_id=zone_id,
        name=name,
        depth=depth,
        depth_norm=depth_norm,
        pop_norm=pop_norm,
        vulnerable_share_norm=vulnerable_share_norm,
        risk_score=risk_score,
        risk_level=risk_level,
        affected_people=affected_people,
        priority=priority,
        population=pop,
        vulnerable_share=vuln,
        lat=lat,
        lon=lon,
        node=node,
    )


def calculate_all_zones_risk(
    zones: Sequence[Union[Zone, Dict[str, Any]]],
    flood_polygons: Sequence[FloodPolygon],
    severity: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
) -> List[ZoneRisk]:
    """Compute risk assessment for all population zones."""
    if not zones:
        return []

    max_population = max(
        (
            int(z.get("population", 0) if hasattr(z, "get") else z["population"])
            for z in zones
        ),
        default=0,
    )

    return [
        calculate_zone_risk(
            zone=z,
            flood_polygons=flood_polygons,
            max_population=max_population,
            severity=severity,
            config=config,
        )
        for z in zones
    ]


def calculate_edge_risk(
    u: int,
    v: int,
    data: Dict[str, Any],
    graph: nx.Graph,
    flood_polygons: Sequence[FloodPolygon],
    severity: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
) -> EdgeRisk:
    """
    Compute risk for a single road edge.
    Formulas from RESQ-X spec:
    - edge_depth = depth of deepest flood polygon containing midpoint
      (or sampled points along geometry), times severity.
    - if edge_depth >= 1.0: edge is impassable (cost = inf).
    - otherwise: edge_cost = length * (1 + 5 * min(edge_depth / 1.0, 1.0)).
    """
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}
    length = float(data.get("length", 0.0))

    # Determine points to evaluate along edge
    sample_fractions = cfg.get("edge_sample_fractions", [0.5])
    geom = data.get("geometry")

    if geom is not None and hasattr(geom, "interpolate"):
        pts = [geom.interpolate(f, normalized=True) for f in sample_fractions]
    else:
        # Fallback to straight-line midpoint between node coordinates
        u_node = graph.nodes.get(u, {})
        v_node = graph.nodes.get(v, {})
        ux = float(u_node.get("x", 0.0))
        uy = float(u_node.get("y", 0.0))
        vx = float(v_node.get("x", 0.0))
        vy = float(v_node.get("y", 0.0))
        mid = Point((ux + vx) / 2.0, (uy + vy) / 2.0)
        pts = [mid]

    # Find deepest flood polygon containing any sample point
    max_d = 0.0
    for pt in pts:
        for poly in flood_polygons:
            if poly.contains_point(pt):
                if poly.depth_m > max_d:
                    max_d = poly.depth_m

    edge_depth = max(0.0, max_d * severity)

    impassable_depth = float(cfg["edge_impassable_depth"])
    penalty_mult = float(cfg["edge_penalty_multiplier"])
    depth_norm_max = float(cfg["edge_depth_norm_max"])

    if edge_depth >= impassable_depth:
        impassable = True
        edge_cost = float("inf")
    else:
        impassable = False
        penalty = penalty_mult * min(edge_depth / depth_norm_max, 1.0)
        edge_cost = length * (1.0 + penalty)

    return EdgeRisk(
        u=int(u),
        v=int(v),
        length=length,
        edge_depth=edge_depth,
        edge_cost=edge_cost,
        impassable=impassable,
    )


def calculate_all_edges_risk(
    graph: nx.DiGraph,
    flood_polygons: Sequence[FloodPolygon],
    severity: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[Tuple[int, int], EdgeRisk]:
    """Compute EdgeRisk for all edges in the graph."""
    edge_risks: Dict[Tuple[int, int], EdgeRisk] = {}
    for u, v, data in graph.edges(data=True):
        risk = calculate_edge_risk(
            u=u,
            v=v,
            data=data,
            graph=graph,
            flood_polygons=flood_polygons,
            severity=severity,
            config=config,
        )
        edge_risks[(int(u), int(v))] = risk
    return edge_risks


def apply_edge_risks_to_graph(
    graph: nx.DiGraph,
    flood_polygons: Sequence[FloodPolygon],
    severity: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
    inplace: bool = False,
) -> nx.DiGraph:
    """Annotate graph edges with edge_depth, edge_cost, and impassable."""
    target_graph = graph if inplace else graph.copy()
    edge_risks = calculate_all_edges_risk(
        graph=target_graph,
        flood_polygons=flood_polygons,
        severity=severity,
        config=config,
    )

    for (u, v), risk in edge_risks.items():
        if target_graph.has_edge(u, v):
            target_graph[u][v]["edge_depth"] = risk.edge_depth
            target_graph[u][v]["edge_cost"] = risk.edge_cost
            target_graph[u][v]["impassable"] = risk.impassable

    return target_graph


def run_risk_engine(
    state: ScenarioState,
    config: Optional[Dict[str, Any]] = None,
    annotate_graph: bool = True,
) -> RiskAssessmentResult:
    """
    Run complete Module 1 risk engine for a ScenarioState.
    Returns RiskAssessmentResult containing zone risks and edge summary.
    Optionally annotates state.graph with edge risk metrics in-place.
    """
    zones_risk = calculate_all_zones_risk(
        zones=state.zones,
        flood_polygons=state.flood_polygons,
        severity=state.severity,
        config=config,
    )

    edge_risks = calculate_all_edges_risk(
        graph=state.graph,
        flood_polygons=state.flood_polygons,
        severity=state.severity,
        config=config,
    )

    if annotate_graph:
        for (u, v), risk in edge_risks.items():
            if state.graph.has_edge(u, v):
                state.graph[u][v]["edge_depth"] = risk.edge_depth
                state.graph[u][v]["edge_cost"] = risk.edge_cost
                state.graph[u][v]["impassable"] = risk.impassable

    total_affected = sum(z.affected_people for z in zones_risk)
    impassable_count = sum(1 for r in edge_risks.values() if r.impassable)

    return RiskAssessmentResult(
        severity=state.severity,
        zones=zones_risk,
        total_affected_people=total_affected,
        impassable_edge_count=impassable_count,
    )
