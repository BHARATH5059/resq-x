from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from ortools.sat.python import cp_model

from app.models.schemas import (
    EvacuationRoutingResult,
    OptimizationResult,
    OptimizationTotals,
    ResourceUtilisation,
    RiskAssessmentResult,
    ShelterAssignment,
    ZoneOptimizationResult,
)
from app.simulation.evacuation import compute_evacuation_routes
from app.simulation.risk_engine import run_risk_engine
from app.simulation.scenario import ScenarioState

# Top-level configurable parameters for Module 3
DEFAULT_OPTIMIZER_CONFIG: Dict[str, Any] = {
    # 6.5 Boat rescue parameters
    "boat_capacity": 400,
    "boat_min_flood_depth": 0.5,
    # 6.2 Rescue team routing penalty factor (lambda)
    "team_travel_cost_penalty": 0.001,
    # CP-SAT integer scaling factor for travel costs
    "cost_integer_scale": 100,
}


def largest_remainder_distribution(
    total_items: int, weights: Dict[str, float]
) -> Dict[str, int]:
    """
    Largest-remainder rounding (Hare-Niemeyer / Hamilton method).
    Guarantees that the sum of allocated integer items equals total_items exactly.
    If total_weight <= 0 or total_items <= 0, returns 0 for all keys.
    """
    if total_items <= 0 or not weights:
        return {k: 0 for k in weights}

    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        return {k: 0 for k in weights}

    quotas = {k: total_items * (w / total_weight) for k, w in weights.items()}
    allocated = {k: int(math.floor(q)) for k, q in quotas.items()}
    remainders = {k: q - allocated[k] for k, q in quotas.items()}
    leftover = total_items - sum(allocated.values())

    # Distribute leftover items to zones with largest remainders
    # Tie-breaker: larger weight, then deterministic key sort
    sorted_keys = sorted(
        weights.keys(),
        key=lambda k: (remainders[k], weights[k], k),
        reverse=True,
    )
    for k in sorted_keys[:leftover]:
        allocated[k] += 1

    return allocated


def optimize_resources(
    state: ScenarioState,
    risk_result: Optional[RiskAssessmentResult] = None,
    routing_result: Optional[EvacuationRoutingResult] = None,
    config: Optional[Dict[str, Any]] = None,
) -> OptimizationResult:
    """
    Module 3: Resource and Shelter Allocator.
    - Base routing: computes road travel costs from base to zones and zones to hospitals.
    - 6.1 Shelter assignment: CP-SAT optimization to maximize assigned people then minimize travel cost.
    - 6.2 Rescue teams: assigns up to available teams to eligible zones maximizing priority net of travel cost.
    - 6.3 Ambulances: assigns to eligible zones ranked by priority * vulnerable_share and pairs with nearest hospital.
    - 6.4 Supplies: distributes food_packets and medical_kits using largest-remainder rounding among reachable zones.
    - 6.5 Boat rescue: rescues up to BOAT_CAPACITY people from cut-off flooded zones (depth >= 0.5m).
    - 6.6 Full output and totals with unmet demand reporting.
    """
    cfg = {**DEFAULT_OPTIMIZER_CONFIG, **(config or {})}

    # 1. Obtain Module 1 and Module 2 outputs if not provided
    if risk_result is None:
        risk_result = run_risk_engine(state)
    if routing_result is None:
        routing_result = compute_evacuation_routes(state)

    zones_by_id = {z.id: z for z in state.zones}
    shelters_by_id = {s.id: s for s in state.shelters}
    hospitals_by_id = {h.id: h for h in state.hospitals}
    risk_by_zone = {zr.zone_id: zr for zr in risk_result.zones}

    # 2. Build filtered graph for Base and Hospital routing
    # Exclude impassable edges, blocked edges, and failed bridges
    failed_bridge_edges: Set[Tuple[int, int]] = set()
    for bridge in state.bridges:
        if bridge.id in state.failed_bridges:
            for u, v in bridge.edges:
                failed_bridge_edges.add((int(u), int(v)))

    blocked_edges: Set[Tuple[int, int]] = set(
        (int(u), int(v)) for u, v in state.blocked_edges
    )

    def is_road_allowed(u: int, v: int) -> bool:
        if (u, v) in blocked_edges or (u, v) in failed_bridge_edges:
            return False
        d = state.graph[u][v]
        if d.get("impassable", False) or d.get("edge_depth", 0.0) >= 1.0:
            return False
        return True

    road_graph = nx.subgraph_view(state.graph, filter_edge=is_road_allowed)

    # 3. Base routing: Dijkstra from rescue base node
    base_node = state.resources.base.node
    base_costs: Dict[int, float] = {}
    base_paths: Dict[int, List[int]] = {}
    if base_node in road_graph:
        try:
            base_costs, base_paths = nx.single_source_dijkstra(
                road_graph, source=base_node, weight="edge_cost"
            )
        except Exception:
            base_costs, base_paths = {}, {}

    base_reachable_zones: Dict[str, float] = {}
    for z in state.zones:
        if z.node in base_paths:
            base_reachable_zones[z.id] = float(base_costs[z.node])

    # 4. Hospital routing for ambulance pairing
    # Eligible hospitals: not failed, and beds_available > 0
    available_hospitals = [
        h
        for h in state.hospitals
        if h.id not in state.failed_hospitals and h.beds_available > 0
    ]

    best_hospital_for_zone: Dict[str, Tuple[Any, float]] = {}
    for z_id in base_reachable_zones:
        z = zones_by_id[z_id]
        if z.node in road_graph and available_hospitals:
            try:
                z_costs, z_paths = nx.single_source_dijkstra(
                    road_graph, source=z.node, weight="edge_cost"
                )
                reachable_h = [
                    (h, z_costs[h.node])
                    for h in available_hospitals
                    if h.node in z_paths
                ]
                if reachable_h:
                    # Lowest route cost from zone
                    reachable_h.sort(key=lambda item: item[1])
                    best_hospital_for_zone[z_id] = reachable_h[0]
            except Exception:
                pass

    # 5. Section 6.5 Boat Rescue
    # Eligible zone: no road route to any available shelter, affected_people > 0, flood depth >= 0.5m
    failed_shelters = set(state.failed_shelters)
    available_shelters = [
        s for s in state.shelters if s.id not in failed_shelters and s.capacity > 0
    ]

    boat_capacity = int(cfg["boat_capacity"])
    min_boat_depth = float(cfg["boat_min_flood_depth"])
    available_boats = int(state.resources.boats)

    boat_eligible_zones: List[str] = []
    for z_id, z in zones_by_id.items():
        z_risk = risk_by_zone[z_id]
        # Check if zone has any road route to available shelters
        z_routes = routing_result.routes.get(z_id, {})
        has_road_route = any(
            z_routes.get(s.id) is not None and z_routes[s.id].status == "ok"
            for s in available_shelters
        )
        if (
            not has_road_route
            and z_risk.affected_people > 0
            and z_risk.depth >= min_boat_depth
        ):
            boat_eligible_zones.append(z_id)

    # Assign boats in order of priority descending
    boat_eligible_zones.sort(
        key=lambda zid: (risk_by_zone[zid].priority, zid),
        reverse=True,
    )

    boat_rescued_by_zone: Dict[str, int] = {z.id: 0 for z in state.zones}
    boats_used = 0
    for zid in boat_eligible_zones:
        if available_boats > 0:
            z_aff = risk_by_zone[zid].affected_people
            rescued = min(z_aff, boat_capacity)
            boat_rescued_by_zone[zid] = rescued
            available_boats -= 1
            boats_used += 1

    # 6. Section 6.1 Shelter Assignment via OR-Tools CP-SAT
    scale = int(cfg["cost_integer_scale"])
    cp_model_obj = cp_model.CpModel()

    # Decision variables x[z_id, s_id]
    var_map: Dict[Tuple[str, str], Any] = {}
    for z_id in zones_by_id:
        z_risk = risk_by_zone[z_id]
        # Note: zones cut off and rescued by boat have no shelter routes anyway
        if z_risk.affected_people <= 0:
            continue
        z_routes = routing_result.routes.get(z_id, {})
        for s in available_shelters:
            s_id = s.id
            route = z_routes.get(s_id)
            if route is not None and route.status == "ok":
                ub = min(z_risk.affected_people, s.capacity)
                var = cp_model_obj.NewIntVar(0, ub, f"x_{z_id}_{s_id}")
                var_map[(z_id, s_id)] = var

    # Constraint: sum over shelters for a zone <= affected_people
    for z_id in zones_by_id:
        z_vars = [
            var_map[(z_id, s.id)]
            for s in available_shelters
            if (z_id, s.id) in var_map
        ]
        if z_vars:
            cp_model_obj.Add(sum(z_vars) <= risk_by_zone[z_id].affected_people)

    # Constraint: sum over zones for a shelter <= shelter capacity
    for s in available_shelters:
        s_vars = [
            var_map[(z_id, s.id)]
            for z_id in zones_by_id
            if (z_id, s.id) in var_map
        ]
        if s_vars:
            cp_model_obj.Add(sum(s_vars) <= s.capacity)

    assignments_by_zone: Dict[str, List[ShelterAssignment]] = {
        z.id: [] for z in state.zones
    }
    assigned_count_by_zone: Dict[str, int] = {z.id: 0 for z in state.zones}

    if var_map:
        # Phase 1: Maximise total people assigned
        cp_model_obj.Maximize(sum(var_map.values()))
        solver = cp_model.CpSolver()
        p1_status = solver.Solve(cp_model_obj)

        if p1_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            max_assigned_people = int(solver.ObjectiveValue())

            # Phase 2: Fix total people assigned to max, minimize total travel cost
            cp_model_phase2 = cp_model.CpModel()
            var_map_p2: Dict[Tuple[str, str], Any] = {}
            for (z_id, s_id), old_var in var_map.items():
                ub = min(risk_by_zone[z_id].affected_people, shelters_by_id[s_id].capacity)
                var_map_p2[(z_id, s_id)] = cp_model_phase2.NewIntVar(
                    0, ub, f"x2_{z_id}_{s_id}"
                )

            # Re-add zone and shelter constraints
            for z_id in zones_by_id:
                z_vars = [
                    var_map_p2[(z_id, s.id)]
                    for s in available_shelters
                    if (z_id, s.id) in var_map_p2
                ]
                if z_vars:
                    cp_model_phase2.Add(
                        sum(z_vars) <= risk_by_zone[z_id].affected_people
                    )

            for s in available_shelters:
                s_vars = [
                    var_map_p2[(z_id, s.id)]
                    for z_id in zones_by_id
                    if (z_id, s.id) in var_map_p2
                ]
                if s_vars:
                    cp_model_phase2.Add(sum(s_vars) <= s.capacity)

            # Fix people assigned == max_assigned_people
            cp_model_phase2.Add(sum(var_map_p2.values()) == max_assigned_people)

            # Minimise sum(people * route_cost * scale)
            objective_terms = [
                var_map_p2[(z_id, s_id)]
                * int(
                    round(
                        routing_result.routes[z_id][s_id].cost * scale
                    )
                )
                for (z_id, s_id) in var_map_p2
            ]
            cp_model_phase2.Minimize(sum(objective_terms))

            p2_status = solver.Solve(cp_model_phase2)
            if p2_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                for (z_id, s_id), var in var_map_p2.items():
                    val = int(solver.Value(var))
                    if val > 0:
                        route = routing_result.routes[z_id][s_id]
                        assignment = ShelterAssignment(
                            shelter_id=s_id,
                            shelter_name=shelters_by_id[s_id].name,
                            people=val,
                            route_cost=route.cost,
                            route_length=route.length,
                        )
                        assignments_by_zone[z_id].append(assignment)
                        assigned_count_by_zone[z_id] += val

    # 7. Section 6.2 Rescue Teams
    # Eligible: affected_people > 0 and reachable from base
    team_eligible = [
        z_id
        for z_id in base_reachable_zones
        if risk_by_zone[z_id].affected_people > 0
    ]
    lambda_cost = float(cfg["team_travel_cost_penalty"])
    # Score = priority - lambda * base_travel_cost
    team_eligible.sort(
        key=lambda zid: (
            risk_by_zone[zid].priority - lambda_cost * base_reachable_zones[zid],
            risk_by_zone[zid].priority,
            zid,
        ),
        reverse=True,
    )

    total_teams = int(state.resources.rescue_teams)
    teams_assigned_zones = set(team_eligible[:total_teams])
    rescue_teams_used = len(teams_assigned_zones)

    # 8. Section 6.3 Ambulances
    # Eligible: affected_people > 0, reachable from base, and has route to non-failed hospital with beds
    amb_eligible = [
        z_id
        for z_id in base_reachable_zones
        if risk_by_zone[z_id].affected_people > 0 and z_id in best_hospital_for_zone
    ]
    # Rank by priority * vulnerable_share
    amb_eligible.sort(
        key=lambda zid: (
            risk_by_zone[zid].priority * zones_by_id[zid].vulnerable_share,
            zid,
        ),
        reverse=True,
    )

    total_amb = int(state.resources.ambulances)
    amb_assigned_zones = set(amb_eligible[:total_amb])
    ambulances_used = len(amb_assigned_zones)

    # 9. Section 6.4 Supplies Distribution via Largest-Remainder Rounding
    # Distribute among zones reachable from base
    reachable_list = list(base_reachable_zones.keys())
    food_weights = {
        zid: float(risk_by_zone[zid].affected_people) for zid in reachable_list
    }
    kits_weights = {
        zid: float(
            risk_by_zone[zid].affected_people * zones_by_id[zid].vulnerable_share
        )
        for zid in reachable_list
    }

    food_allocated = largest_remainder_distribution(
        total_items=int(state.resources.food_packets),
        weights=food_weights,
    )
    kits_allocated = largest_remainder_distribution(
        total_items=int(state.resources.medical_kits),
        weights=kits_weights,
    )

    # 10. Assemble Zone Results and Totals (6.6)
    zone_results: List[ZoneOptimizationResult] = []
    tot_affected = 0
    tot_assigned = 0
    tot_rescued_boat = 0
    tot_unmet = 0
    tot_travel_cost = 0.0

    for zone in state.zones:
        z_id = zone.id
        z_risk = risk_by_zone[z_id]
        assigned_shelter = assigned_count_by_zone[z_id]
        rescued_boat = boat_rescued_by_zone[z_id]
        unmet = max(0, z_risk.affected_people - assigned_shelter - rescued_boat)

        has_team = z_id in teams_assigned_zones
        has_amb = z_id in amb_assigned_zones
        h_info = best_hospital_for_zone.get(z_id) if has_amb else None
        h_id = h_info[0].id if h_info else None
        h_name = h_info[0].name if h_info else None

        f_packs = food_allocated.get(z_id, 0)
        m_kits = kits_allocated.get(z_id, 0)

        # Accumulate travel cost (people x route cost)
        for sa in assignments_by_zone[z_id]:
            tot_travel_cost += sa.people * sa.route_cost

        tot_affected += z_risk.affected_people
        tot_assigned += assigned_shelter
        tot_rescued_boat += rescued_boat
        tot_unmet += unmet

        zone_results.append(
            ZoneOptimizationResult(
                zone_id=z_id,
                name=zone.name,
                risk_level=z_risk.risk_level,
                affected_people=z_risk.affected_people,
                shelter_assignments=assignments_by_zone[z_id],
                assigned_to_shelters=assigned_shelter,
                rescued_by_boat=rescued_boat,
                unmet_people=unmet,
                rescue_team=has_team,
                ambulance=has_amb,
                hospital_id=h_id,
                hospital_name=h_name,
                food_packets=f_packs,
                medical_kits=m_kits,
            )
        )

    utilisation = ResourceUtilisation(
        rescue_teams_used=rescue_teams_used,
        rescue_teams_available=int(state.resources.rescue_teams),
        ambulances_used=ambulances_used,
        ambulances_available=int(state.resources.ambulances),
        boats_used=boats_used,
        boats_available=int(state.resources.boats),
        food_packets_distributed=sum(food_allocated.values()),
        food_packets_available=int(state.resources.food_packets),
        medical_kits_distributed=sum(kits_allocated.values()),
        medical_kits_available=int(state.resources.medical_kits),
    )

    totals = OptimizationTotals(
        total_affected_people=tot_affected,
        total_assigned_to_shelters=tot_assigned,
        total_rescued_by_boat=tot_rescued_boat,
        total_unmet_people=tot_unmet,
        total_travel_cost=float(tot_travel_cost),
        resource_utilisation=utilisation,
    )

    return OptimizationResult(
        zones=zone_results,
        totals=totals,
    )
