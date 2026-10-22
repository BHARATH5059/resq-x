from __future__ import annotations

import json
import math
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.schemas import (
    FailureEventRequest,
    HealthResponse,
    SimulateRequest,
)
from app.simulation.failure_simulator import (
    apply_failure,
    ensure_baseline_initialized,
    reset,
    run_simulation,
)
from app.simulation.risk_engine import apply_edge_risks_to_graph
from app.simulation.scenario import ScenarioState, load_scenario_state

router = APIRouter()

# Thread-safe lock protecting the in-memory scenario state
_state_lock = threading.Lock()
_scenario_state: Optional[ScenarioState] = None


def get_scenario_state() -> ScenarioState:
    """Dependency returning the shared in-memory ScenarioState singleton."""
    global _scenario_state
    if _scenario_state is None:
        with _state_lock:
            if _scenario_state is None:
                _scenario_state = load_scenario_state("data")
                ensure_baseline_initialized(_scenario_state)
    return _scenario_state


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize data for JSON serialization.
    Replaces float('inf'), -float('inf'), and NaN with None (JSON null).
    Converts Pydantic models and objects to dictionaries.
    """
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]
    elif hasattr(obj, "model_dump"):
        return sanitize_for_json(obj.model_dump())
    elif hasattr(obj, "__dict__"):
        return sanitize_for_json(obj.__dict__)
    return obj


# =====================================================================
# API Endpoints
# =====================================================================

@router.get("/health", response_model=HealthResponse)
def get_health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/scenario")
def get_scenario(state: ScenarioState = Depends(get_scenario_state)) -> JSONResponse:
    """
    Static map data as GeoJSON ([lon, lat]):
    - zones: FeatureCollection of Point geometries
    - shelters: FeatureCollection of Point geometries
    - hospitals: FeatureCollection of Point geometries
    - relief base: Feature (Point geometry)
    - flood polygons: FeatureCollection of Polygon geometries
    - bridges (critical crossings): FeatureCollection of LineString geometries
    """
    with _state_lock:
        # Zones
        zones_fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": z.id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(z.lon), float(z.lat)],
                    },
                    "properties": {
                        "id": z.id,
                        "name": z.name,
                        "population": int(z.population),
                        "vulnerable_share": float(z.vulnerable_share),
                        "node": int(z.node),
                        "snap_m": float(z.snap_m),
                    },
                }
                for z in state.zones
            ],
        }

        # Shelters
        shelters_fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": s.id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(s.lon), float(s.lat)],
                    },
                    "properties": {
                        "id": s.id,
                        "name": s.name,
                        "capacity": int(s.capacity),
                        "node": int(s.node),
                        "snap_m": float(s.snap_m),
                    },
                }
                for s in state.shelters
            ],
        }

        # Hospitals
        hospitals_fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": h.id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(h.lon), float(h.lat)],
                    },
                    "properties": {
                        "id": h.id,
                        "name": h.name,
                        "beds_available": int(h.beds_available),
                        "node": int(h.node),
                        "snap_m": float(h.snap_m),
                    },
                }
                for h in state.hospitals
            ],
        }

        # Relief Base
        base_feature = {
            "type": "Feature",
            "id": "base",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    float(state.resources.base.lon),
                    float(state.resources.base.lat),
                ],
            },
            "properties": {
                "name": state.resources.base.name,
                "lat": float(state.resources.base.lat),
                "lon": float(state.resources.base.lon),
                "node": int(state.resources.base.node),
                "rescue_teams": int(state.resources.rescue_teams),
                "ambulances": int(state.resources.ambulances),
                "boats": int(state.resources.boats),
                "food_packets": int(state.resources.food_packets),
                "medical_kits": int(state.resources.medical_kits),
            },
        }

        # Flood Polygons
        flood_features = []
        for fp in state.flood_polygons:
            geom_dict = None
            if hasattr(fp.geometry, "__geo_interface__"):
                geom_dict = fp.geometry.__geo_interface__
            elif fp.raw_geojson and "geometry" in fp.raw_geojson:
                geom_dict = fp.raw_geojson["geometry"]

            flood_features.append(
                {
                    "type": "Feature",
                    "id": fp.id,
                    "geometry": geom_dict,
                    "properties": {
                        "id": fp.id,
                        "name": fp.name,
                        "depth_m": float(fp.depth_m),
                        "simulated": bool(fp.simulated),
                    },
                }
            )
        flood_fc = {"type": "FeatureCollection", "features": flood_features}

        # Bridges (drawn as LineStrings in [lon, lat])
        bridge_features = []
        for b in state.bridges:
            for u, v in b.edges:
                edge_data = state.graph.get_edge_data(u, v, default={})
                geom = edge_data.get("geometry")
                if geom is not None and hasattr(geom, "coords"):
                    coords = [list(c) for c in geom.coords]
                else:
                    u_node = state.graph.nodes.get(u, {})
                    v_node = state.graph.nodes.get(v, {})
                    coords = [
                        [float(u_node.get("x", 0.0)), float(u_node.get("y", 0.0))],
                        [float(v_node.get("x", 0.0)), float(v_node.get("y", 0.0))],
                    ]

                bridge_features.append(
                    {
                        "type": "Feature",
                        "id": f"{b.id}_{u}_{v}",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "bridge_id": b.id,
                            "bridge_name": b.name,
                            "u": int(u),
                            "v": int(v),
                        },
                    }
                )
        bridges_fc = {"type": "FeatureCollection", "features": bridge_features}

        data = {
            "zones": zones_fc,
            "shelters": shelters_fc,
            "hospitals": hospitals_fc,
            "relief_base": base_feature,
            "base": base_feature,
            "flood_polygons": flood_fc,
            "bridges": bridges_fc,
            "crossings": bridges_fc,
        }
        return JSONResponse(content=sanitize_for_json(data))


@router.get("/roads")
def get_roads(state: ScenarioState = Depends(get_scenario_state)) -> JSONResponse:
    """
    Returns all road edges as GeoJSON LineStrings with edge_depth,
    impassable and blocked at the current state.
    """
    with _state_lock:
        # Ensure edge risks are applied to graph for current severity
        apply_edge_risks_to_graph(
            graph=state.graph,
            flood_polygons=state.flood_polygons,
            severity=state.severity,
            inplace=True,
        )

        failed_bridge_edges = set()
        for b in state.bridges:
            if b.id in state.failed_bridges:
                for u, v in b.edges:
                    failed_bridge_edges.add((int(u), int(v)))

        features = []
        for u, v, d in state.graph.edges(data=True):
            u_int, v_int = int(u), int(v)
            geom = d.get("geometry")
            if geom is not None and hasattr(geom, "coords"):
                coords = [list(c) for c in geom.coords]
            else:
                u_node = state.graph.nodes.get(u, {})
                v_node = state.graph.nodes.get(v, {})
                coords = [
                    [float(u_node.get("x", 0.0)), float(u_node.get("y", 0.0))],
                    [float(v_node.get("x", 0.0)), float(v_node.get("y", 0.0))],
                ]

            depth = float(d.get("edge_depth", 0.0))
            imp = bool(d.get("impassable", False) or depth >= 1.0)
            blocked = bool(
                (u_int, v_int) in state.blocked_edges
                or (u_int, v_int) in failed_bridge_edges
            )

            raw_cost = d.get("edge_cost")
            clean_cost = (
                round(float(raw_cost), 2)
                if raw_cost is not None and not math.isinf(float(raw_cost)) and not imp
                else None
            )

            features.append(
                {
                    "type": "Feature",
                    "id": f"{u_int}_{v_int}",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "u": u_int,
                        "v": v_int,
                        "length": round(float(d.get("length", 0.0)), 2),
                        "edge_depth": round(depth, 3),
                        "edge_cost": clean_cost,
                        "impassable": imp,
                        "blocked": blocked,
                        "name": d.get("name") or "",
                    },
                }
            )

        roads_fc = {"type": "FeatureCollection", "features": features}
        return JSONResponse(content=sanitize_for_json(roads_fc))


@router.post("/simulate")
def simulate_scenario(
    req: SimulateRequest = SimulateRequest(),
    state: ScenarioState = Depends(get_scenario_state),
) -> JSONResponse:
    """
    POST /simulate:
    Body: {severity: 1.0, resources: {optional overrides}}
    Returns: {risk, routes, allocation, unmet, totals} with route_geojson per pair,
    and saves the plan as the baseline.
    """
    with _state_lock:
        state.severity = float(req.severity)

        if req.resources:
            for k, v in req.resources.items():
                if hasattr(state.resources, k):
                    setattr(state.resources, k, int(v))

        # Re-run simulation and save as baseline
        plan = run_simulation(state, save_as_baseline=True)

        resp_data = {
            "severity": plan.severity,
            "risk": plan.risk,
            "routes": plan.routes,
            "allocation": plan.allocation,
            "unmet": plan.unmet,
            "totals": plan.totals,
        }
        return JSONResponse(content=sanitize_for_json(resp_data))


@router.post("/failure")
def apply_failure_event(
    req: FailureEventRequest,
    state: ScenarioState = Depends(get_scenario_state),
) -> JSONResponse:
    """
    POST /failure:
    Body: {type, id, amount?}
    Validates IDs (404/422 with clear messages) and returns {plan, diff}.
    """
    with _state_lock:
        ev_type = req.type
        known_bridge_ids = [b.id for b in state.bridges]
        known_shelter_ids = [s.id for s in state.shelters]
        known_hospital_ids = [h.id for h in state.hospitals]
        known_resource_fields = [
            "rescue_teams",
            "ambulances",
            "boats",
            "food_packets",
            "medical_kits",
        ]

        # 1. Type validation
        supported_types = {
            "block_bridge",
            "block_edge",
            "fail_shelter",
            "fill_shelter",
            "fail_hospital",
            "reduce_resources",
            "reset",
        }
        if ev_type not in supported_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown failure type '{ev_type}'. Supported types: {sorted(supported_types)}",
            )

        # 2. ID and parameter validation
        if ev_type == "block_bridge":
            if not req.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Missing required parameter 'id' for 'block_bridge'.",
                )
            if req.id not in known_bridge_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Bridge '{req.id}' not found. Available bridges: {known_bridge_ids}",
                )

        elif ev_type in ("fail_shelter", "fill_shelter"):
            if not req.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Missing required parameter 'id' for '{ev_type}'.",
                )
            if req.id not in known_shelter_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Shelter '{req.id}' not found. Available shelters: {known_shelter_ids}",
                )

        elif ev_type == "fail_hospital":
            if not req.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Missing required parameter 'id' for 'fail_hospital'.",
                )
            if req.id not in known_hospital_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hospital '{req.id}' not found. Available hospitals: {known_hospital_ids}",
                )

        elif ev_type == "block_edge":
            edge = req.edge
            if edge is None and req.id:
                try:
                    edge = [int(x) for x in req.id.replace("->", ",").split(",")]
                except Exception:
                    pass
            if not edge or len(edge) < 2:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Missing or invalid parameter 'edge' [u, v] for 'block_edge'.",
                )
            u, v = int(edge[0]), int(edge[1])
            if not state.graph.has_edge(u, v):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Edge ({u}, {v}) not found in the road network.",
                )

        elif ev_type == "reduce_resources":
            field = req.field or req.id
            if not field or field not in known_resource_fields:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid resource field '{field}'. Allowed: {known_resource_fields}",
                )
            if req.amount is None or req.amount < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Missing or invalid non-negative parameter 'amount' for 'reduce_resources'.",
                )

        # 3. Apply failure
        diff = apply_failure(state, req)
        resp_data = {
            "plan": diff.plan,
            "diff": diff,
        }
        return JSONResponse(content=sanitize_for_json(resp_data))


@router.post("/reset")
def reset_scenario(state: ScenarioState = Depends(get_scenario_state)) -> JSONResponse:
    """
    POST /reset:
    Clears all cumulative failures and restores scenario back to baseline.
    """
    with _state_lock:
        diff = reset(state)
        resp_data = {
            "status": "ok",
            "message": "Scenario reset to baseline.",
            "plan": diff.plan,
            "diff": diff,
        }
        return JSONResponse(content=sanitize_for_json(resp_data))
