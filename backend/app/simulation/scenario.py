from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import shape
from shapely.prepared import prep

from app.models.schemas import (
    Bridge,
    FloodZoneFeature,
    Hospital,
    ResourceBase,
    Resources,
    Shelter,
    Zone,
)


@dataclass
class FloodPolygon:
    id: str
    name: str
    depth_m: float
    geometry: Any
    simulated: bool = True
    raw_geojson: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Cache prepared geometry for rapid spatial querying
        if self.geometry is not None:
            self._prep = prep(self.geometry)
        else:
            self._prep = None

    def contains_point(self, pt: Any) -> bool:
        """Check if point is contained or intersected by the polygon."""
        if self.geometry is None:
            return False
        if self._prep is not None:
            return bool(self._prep.intersects(pt))
        return bool(self.geometry.intersects(pt))

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


def convert_multidigraph_to_digraph(
    G: Union[nx.MultiDiGraph, nx.DiGraph],
    bridge_edges: Optional[Set[Tuple[int, int]]] = None,
) -> nx.DiGraph:
    """
    Convert MultiDiGraph to DiGraph:
    - Keeps shortest `length` edge for each (u, v).
    - Preserves bridge edges.
    - Preserves node and edge attributes.
    """
    if isinstance(G, nx.DiGraph) and not isinstance(G, nx.MultiDiGraph):
        return G.copy()

    D = nx.DiGraph()
    D.graph.update(G.graph)

    for n, data in G.nodes(data=True):
        D.add_node(int(n), **data)

    bridge_set = bridge_edges or set()

    for u, v, k, data in G.edges(keys=True, data=True):
        u_int, v_int = int(u), int(v)
        length = float(data.get("length", 0.0))
        is_bridge = (u_int, v_int) in bridge_set

        if not D.has_edge(u_int, v_int):
            D.add_edge(u_int, v_int, **data)
        else:
            current_len = float(D[u_int][v_int].get("length", float("inf")))
            current_is_bridge = (u_int, v_int) in bridge_set

            # If current edge is bridge and new is not, keep bridge unless new is also bridge
            if is_bridge and not current_is_bridge:
                D.add_edge(u_int, v_int, **data)
            elif (not current_is_bridge or is_bridge) and length < current_len:
                D.add_edge(u_int, v_int, **data)

    return D


@dataclass
class ScenarioState:
    """
    Core state for RESQ-X simulation. Holds:
    - graph: DiGraph
    - zones: list of Zone models
    - shelters: list of Shelter models
    - hospitals: list of Hospital models
    - resources: Resources model or dict
    - flood_polygons: list of FloodPolygon objects
    - bridges: list of Bridge models
    - severity: float (default 1.0)
    - blocked_edges: set of (u, v) tuples
    - failed_shelters: set of shelter IDs
    - failed_hospitals: set of hospital IDs
    - failed_bridges: set of bridge IDs
    - baseline: plan produced by the last /simulate
    - facilities: optional raw GeoJSON
    """

    graph: nx.DiGraph
    zones: List[Zone]
    shelters: List[Shelter]
    hospitals: List[Hospital]
    resources: Resources
    flood_polygons: List[FloodPolygon]
    bridges: List[Bridge] = field(default_factory=list)
    severity: float = 1.0
    blocked_edges: Set[Tuple[int, int]] = field(default_factory=set)
    failed_shelters: Set[str] = field(default_factory=set)
    failed_hospitals: Set[str] = field(default_factory=set)
    failed_bridges: Set[str] = field(default_factory=set)
    baseline: Optional[Any] = None
    facilities: Optional[Dict[str, Any]] = None

    def clear_failures(self) -> None:
        """Clear all cumulative failures."""
        self.blocked_edges.clear()
        self.failed_shelters.clear()
        self.failed_hospitals.clear()
        self.failed_bridges.clear()

    def reset(self) -> None:
        """Reset scenario state back to baseline conditions."""
        self.severity = 1.0
        self.clear_failures()

    def copy(self) -> ScenarioState:
        """Create a shallow copy with isolated failure sets and graph copy."""
        return ScenarioState(
            graph=self.graph.copy(),
            zones=list(self.zones),
            shelters=list(self.shelters),
            hospitals=list(self.hospitals),
            resources=self.resources,
            flood_polygons=list(self.flood_polygons),
            bridges=list(self.bridges),
            severity=self.severity,
            blocked_edges=set(self.blocked_edges),
            failed_shelters=set(self.failed_shelters),
            failed_hospitals=set(self.failed_hospitals),
            failed_bridges=set(self.failed_bridges),
            baseline=self.baseline,
            facilities=self.facilities,
        )


def _resolve_data_dir(data_dir: Union[str, Path]) -> Path:
    p = Path(data_dir)
    if p.exists() and p.is_dir():
        return p
    # Look relative to project root
    candidate = Path(__file__).resolve().parent.parent.parent.parent / data_dir
    if candidate.exists() and candidate.is_dir():
        return candidate
    candidate_alt = Path(__file__).resolve().parent.parent.parent / data_dir
    if candidate_alt.exists() and candidate_alt.is_dir():
        return candidate_alt
    return p


def load_scenario_state(data_dir: Union[str, Path] = "data") -> ScenarioState:
    """
    Load ScenarioState from static files in data directory.
    Does not modify any files in data/.
    """
    base_dir = _resolve_data_dir(data_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"Data directory '{base_dir}' does not exist.")

    # 1. Bridges
    bridges_path = base_dir / "bridges.json"
    bridges_list: List[Bridge] = []
    bridge_edge_set: Set[Tuple[int, int]] = set()
    if bridges_path.exists():
        with open(bridges_path, "r", encoding="utf-8") as f:
            raw_bridges = json.load(f)
            for b in raw_bridges:
                bridge_model = Bridge(
                    id=str(b["id"]),
                    name=str(b["name"]),
                    edges=[[int(u), int(v)] for u, v in b["edges"]],
                )
                bridges_list.append(bridge_model)
                for u, v in bridge_model.edges:
                    bridge_edge_set.add((u, v))

    # 2. Road graph
    graph_path = base_dir / "road_graph.graphml"
    if not graph_path.exists():
        raise FileNotFoundError(f"Missing road graph at {graph_path}")
    raw_graph = ox.load_graphml(graph_path)
    di_graph = convert_multidigraph_to_digraph(raw_graph, bridge_edges=bridge_edge_set)

    # 3. Shelters
    shelters_path = base_dir / "shelters.csv"
    shelters_df = pd.read_csv(shelters_path)
    shelters = [
        Shelter(
            id=str(row["id"]),
            name=str(row["name"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            capacity=int(row["capacity"]),
            node=int(row["node"]),
            snap_m=float(row.get("snap_m", 0.0)),
        )
        for _, row in shelters_df.iterrows()
    ]

    # 4. Hospitals
    hospitals_path = base_dir / "hospitals.csv"
    hospitals_df = pd.read_csv(hospitals_path)
    hospitals = [
        Hospital(
            id=str(row["id"]),
            name=str(row["name"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            beds_available=int(row["beds_available"]),
            node=int(row["node"]),
            snap_m=float(row.get("snap_m", 0.0)),
        )
        for _, row in hospitals_df.iterrows()
    ]

    # 5. Population zones
    zones_path = base_dir / "population_zones.csv"
    zones_df = pd.read_csv(zones_path)
    zones = [
        Zone(
            id=str(row["id"]),
            name=str(row["name"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            population=int(row["population"]),
            vulnerable_share=float(row["vulnerable_share"]),
            node=int(row["node"]),
            snap_m=float(row.get("snap_m", 0.0)),
        )
        for _, row in zones_df.iterrows()
    ]

    # 6. Resources
    resources_path = base_dir / "resources.json"
    with open(resources_path, "r", encoding="utf-8") as f:
        res_data = json.load(f)
        resources = Resources(
            base=ResourceBase(
                name=str(res_data["base"]["name"]),
                lat=float(res_data["base"]["lat"]),
                lon=float(res_data["base"]["lon"]),
                node=int(res_data["base"]["node"]),
            ),
            rescue_teams=int(res_data["rescue_teams"]),
            ambulances=int(res_data["ambulances"]),
            boats=int(res_data["boats"]),
            food_packets=int(res_data["food_packets"]),
            medical_kits=int(res_data["medical_kits"]),
        )

    # 7. Flood zones
    flood_path = base_dir / "flood_zones.geojson"
    flood_polygons: List[FloodPolygon] = []
    if flood_path.exists():
        with open(flood_path, "r", encoding="utf-8") as f:
            flood_data = json.load(f)
            for feat in flood_data.get("features", []):
                geom = shape(feat["geometry"])
                flood_polygons.append(
                    FloodPolygon(
                        id=str(feat["properties"].get("id", "")),
                        name=str(feat["properties"].get("name", "")),
                        depth_m=float(feat["properties"].get("depth_m", 0.0)),
                        geometry=geom,
                        simulated=bool(feat["properties"].get("simulated", True)),
                        raw_geojson=feat,
                    )
                )

    # 8. Facilities (optional display only)
    facilities_path = base_dir / "facilities.geojson"
    facilities_data = None
    if facilities_path.exists():
        with open(facilities_path, "r", encoding="utf-8") as f:
            facilities_data = json.load(f)

    return ScenarioState(
        graph=di_graph,
        zones=zones,
        shelters=shelters,
        hospitals=hospitals,
        resources=resources,
        flood_polygons=flood_polygons,
        bridges=bridges_list,
        severity=1.0,
        blocked_edges=set(),
        failed_shelters=set(),
        failed_hospitals=set(),
        failed_bridges=set(),
        baseline=None,
        facilities=facilities_data,
    )
