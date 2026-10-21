from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import networkx as nx
import pytest
from shapely.geometry import Polygon

# Ensure backend/app is importable
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.schemas import (
    Bridge,
    Hospital,
    ResourceBase,
    Resources,
    Shelter,
    Zone,
)
from app.simulation.scenario import FloodPolygon, ScenarioState, load_scenario_state


@pytest.fixture
def handmade_scenario_state() -> ScenarioState:
    """
    Tiny hand-made test graph fixture (6 nodes, 2 shelters, 1 bridge, 2 zones, 1 flood polygon)
    with fully known, hand-calculated correct answers.

    Topology:
        Node 1 (Flooded Zone P1) --- [100m, flooded] --- Node 2
           |                                                |
        [200m dry]                                    [150m Bridge B1]
           |                                                |
        Node 3 (Rescue Base)     --- [120m dry]       --- Node 4
           |                                                |
        [100m dry]                                       [100m dry]
           |                                                |
        Node 5 (Shelter S1)                               Node 6 (Shelter S2 & Dry Zone P2)
    """
    G = nx.DiGraph()

    # 6 nodes with known coordinates (lat, lon) -> (y, x)
    node_coords = {
        1: {"lat": 13.000, "lon": 80.200},  # Inside flood polygon F1
        2: {"lat": 13.000, "lon": 80.210},  # Inside flood polygon F1
        3: {"lat": 13.010, "lon": 80.200},  # Dry / Rescue base
        4: {"lat": 13.010, "lon": 80.210},  # Dry
        5: {"lat": 13.020, "lon": 80.200},  # Dry / Shelter S1
        6: {"lat": 13.020, "lon": 80.210},  # Dry / Shelter S2, Zone P2
    }

    for nid, c in node_coords.items():
        G.add_node(nid, y=c["lat"], x=c["lon"])

    # Directed edges with lengths
    edge_defs = [
        (1, 2, 100.0),
        (2, 1, 100.0),
        (1, 3, 200.0),
        (3, 1, 200.0),
        (2, 4, 150.0),  # Bridge B1
        (4, 2, 150.0),  # Bridge B1
        (3, 4, 120.0),
        (4, 3, 120.0),
        (3, 5, 100.0),
        (5, 3, 100.0),
        (4, 6, 100.0),
        (6, 4, 100.0),
    ]

    for u, v, length in edge_defs:
        is_bridge = (u, v) in [(2, 4), (4, 2)]
        G.add_edge(u, v, length=length, bridge="yes" if is_bridge else "no")

    # Bridge B1
    bridges = [
        Bridge(
            id="B1",
            name="Handmade Bridge B1",
            edges=[[2, 4], [4, 2]],
        )
    ]

    # Shelters (2 shelters)
    shelters = [
        Shelter(
            id="S1",
            name="Shelter S1",
            lat=13.020,
            lon=80.200,
            capacity=400,
            node=5,
            snap_m=0.0,
        ),
        Shelter(
            id="S2",
            name="Shelter S2",
            lat=13.020,
            lon=80.210,
            capacity=300,
            node=6,
            snap_m=0.0,
        ),
    ]

    # Hospitals (2 hospitals)
    hospitals = [
        Hospital(
            id="H1",
            name="Hospital H1",
            lat=13.020,
            lon=80.200,
            beds_available=40,
            node=5,
            snap_m=0.0,
        ),
        Hospital(
            id="H2",
            name="Hospital H2",
            lat=13.020,
            lon=80.210,
            beds_available=30,
            node=6,
            snap_m=0.0,
        ),
    ]

    # Population zones (2 zones: P1 flooded, P2 completely dry)
    zones = [
        Zone(
            id="P1",
            name="Flooded Zone",
            lat=13.000,
            lon=80.200,
            population=1000,
            vulnerable_share=0.28,
            node=1,
            snap_m=0.0,
        ),
        Zone(
            id="P2",
            name="Dry Zone",
            lat=13.020,
            lon=80.210,
            population=2000,
            vulnerable_share=0.14,
            node=6,
            snap_m=0.0,
        ),
    ]

    # Flood Polygon F1: depth_m = 0.9m
    # Covering [lon, lat]: [80.195, 12.995] to [80.215, 13.002]
    f1_poly = Polygon(
        [
            [80.195, 12.995],
            [80.215, 12.995],
            [80.215, 13.002],
            [80.195, 13.002],
            [80.195, 12.995],
        ]
    )

    flood_polygons = [
        FloodPolygon(
            id="F1",
            name="South River Flood Zone",
            depth_m=0.9,
            geometry=f1_poly,
            simulated=True,
        )
    ]

    resources = Resources(
        base=ResourceBase(name="Base Station", lat=13.010, lon=80.200, node=3),
        rescue_teams=3,
        ambulances=2,
        boats=2,
        food_packets=500,
        medical_kits=100,
    )

    return ScenarioState(
        graph=G,
        zones=zones,
        shelters=shelters,
        hospitals=hospitals,
        resources=resources,
        flood_polygons=flood_polygons,
        bridges=bridges,
        severity=1.0,
        blocked_edges=set(),
        failed_shelters=set(),
        failed_hospitals=set(),
        failed_bridges=set(),
        baseline=None,
    )


@pytest.fixture
def handmade_expected_values() -> Dict[str, Any]:
    """
    Known, hand-calculated values for the handmade fixture at severity 1.0 and 1.5.
    """
    return {
        "severity_1_0": {
            "P1": {
                "depth": 0.9,
                "depth_norm": 0.6,
                "pop_norm": 0.5,
                "vulnerable_share_norm": 0.8,
                "risk_score": 0.64,
                "risk_level": "high",
                "affected_people": 600,
                "priority": 384.0,
            },
            "P2": {
                "depth": 0.0,
                "depth_norm": 0.0,
                "pop_norm": 1.0,
                "vulnerable_share_norm": 0.4,
                "risk_score": 0.32,
                "risk_level": "medium",
                "affected_people": 0,
                "priority": 0.0,
            },
            "edge_1_2": {
                "edge_depth": 0.9,
                "impassable": False,
                "edge_cost": 550.0,
            },
            "edge_bridge": {
                "edge_depth": 0.0,
                "impassable": False,
                "edge_cost": 150.0,
            },
        },
        "severity_1_5": {
            "P1": {
                "depth": 1.35,
                "depth_norm": 0.9,
                "pop_norm": 0.5,
                "vulnerable_share_norm": 0.8,
                "risk_score": 0.79,
                "risk_level": "critical",
                "affected_people": 900,
                "priority": 711.0,
            },
            "edge_1_2": {
                "edge_depth": 1.35,
                "impassable": True,
                "edge_cost": float("inf"),
            },
        },
    }


@pytest.fixture(scope="session")
def real_scenario_state() -> ScenarioState:
    """Loaded ScenarioState from the real data/ directory (read-only)."""
    return load_scenario_state("data")
