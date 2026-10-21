from __future__ import annotations

import math
from typing import List
import pytest

from app.models.schemas import EvacuationRoutingResult
from app.simulation.evacuation import (
    clear_evacuation_cache,
    compute_evacuation_routes,
    get_routing_cache_key,
)
from app.simulation.scenario import ScenarioState


# ==============================================================================
# SECTION 10 BEHAVIOUR TESTS: ITEMS 3, 4, AND 11
# ==============================================================================


def test_behaviour_3_blocking_bridge_reroutes_traffic(
    handmade_scenario_state: ScenarioState,
):
    """
    Section 10, Test 3:
    'Blocking the bridge removes every route that used it, and the new route avoids it.'
    Tested on the hand-made fixture where Bridge B1 is on edge (2, 4).
    """
    clear_evacuation_cache()
    state_open = handmade_scenario_state.copy()
    result_open = compute_evacuation_routes(state_open)

    # In open state, P1 -> S2 path uses Bridge B1 (node 2 -> node 4)
    route_open = result_open.routes["P1"]["S2"]
    assert route_open.status == "ok"
    assert route_open.path == [1, 2, 4, 6]
    assert pytest.approx(route_open.length) == 350.0  # 100m + 150m (B1) + 100m

    # Confirm Bridge B1 edge (2, 4) is traversed
    open_edges = list(zip(route_open.path[:-1], route_open.path[1:]))
    assert (2, 4) in open_edges

    # Now block Bridge B1
    state_blocked = handmade_scenario_state.copy()
    state_blocked.failed_bridges.add("B1")
    result_blocked = compute_evacuation_routes(state_blocked)

    route_blocked = result_blocked.routes["P1"]["S2"]
    assert route_blocked.status == "ok"
    # New route detours via Node 3 (Rescue base): 1 -> 3 -> 4 -> 6
    assert route_blocked.path == [1, 3, 4, 6]
    assert pytest.approx(route_blocked.length) == 820.0  # 600m + 120m + 100m
    assert pytest.approx(route_blocked.cost) == 820.0

    # Bridge B1 edge (2, 4) is completely avoided by the new route
    blocked_edges = list(zip(route_blocked.path[:-1], route_blocked.path[1:]))
    assert (2, 4) not in blocked_edges
    assert (4, 2) not in blocked_edges


def test_behaviour_4_cutoff_zone_returns_no_route_and_unmet_no_exception(
    handmade_scenario_state: ScenarioState,
):
    """
    Section 10, Test 4:
    'If no path exists, the zone is reported as no_route and its people counted as unmet. No exception.'
    Tested on the hand-made fixture by completely isolating Zone P1.
    """
    clear_evacuation_cache()
    state_isolated = handmade_scenario_state.copy()
    # Block all egress edges from Node 1 (Zone P1)
    state_isolated.blocked_edges.add((1, 2))
    state_isolated.blocked_edges.add((1, 3))

    # Must never raise an exception
    result = compute_evacuation_routes(state_isolated)

    # Check P1 routes to all shelters
    p1_routes = result.routes["P1"]
    for shelter_id, route in p1_routes.items():
        assert route.status == "no_route"
        assert math.isinf(route.cost)
        assert math.isinf(route.length)
        assert route.path == []
        assert route.route_geojson is None

    # Zone P1 must be registered in cut_off_zones
    assert "P1" in result.cut_off_zones

    # People in P1 counted as unmet demand:
    # Population 1000, depth 0.9, depth_norm 0.6 -> affected_people = 600
    assert result.total_unmet_people == 600


def test_behaviour_11_baseline_comparison_real_graph(
    real_scenario_state: ScenarioState, capsys: pytest.CaptureFixture
):
    """
    Section 10, Test 11:
    'Baseline comparison: risk-aware routing avoids at least one flooded edge
     that plain shortest-path uses (test on the real graph, report the numbers).'
    """
    clear_evacuation_cache()
    state = real_scenario_state.copy()
    state.severity = 1.0

    result = compute_evacuation_routes(state)

    avoided_flood_count = 0
    total_pairs = 0
    details: List[str] = []

    for z_id, s_map in result.routes.items():
        for s_id, route in s_map.items():
            total_pairs += 1
            if route.status == "ok" and route.baseline_route and route.baseline_route.status == "ok":
                plain_flooded = route.baseline_route.flooded_edges_count
                risk_flooded = route.flooded_edges_count
                if risk_flooded < plain_flooded:
                    avoided_flood_count += 1
                    diff_flooded = plain_flooded - risk_flooded
                    details.append(
                        f"  Pair {z_id} -> {s_id}: Plain route uses {plain_flooded} flooded edges, "
                        f"Risk-aware uses {risk_flooded} (avoided {diff_flooded} flooded edges; "
                        f"plain len={route.baseline_route.length:.0f}m, risk len={route.length:.0f}m)"
                    )

    # Print numbers as required by Section 10 item 11
    print("\n--- Test 11 Results on Real Graph at Severity 1.0 ---")
    print(
        f"Out of {total_pairs} zone-to-shelter pairs, risk-aware routing avoids flooded edges "
        f"that plain shortest-path uses in {avoided_flood_count} pairs."
    )
    for line in details:
        print(line)

    # Capture output so it shows in pytest logs
    out = capsys.readouterr().out
    print(out)

    # Must avoid flooded edges for at least one pair
    assert avoided_flood_count >= 1


# ==============================================================================
# MODULE 2 UNIT & CACHING TESTS
# ==============================================================================


def test_route_geojson_format(handmade_scenario_state: ScenarioState):
    """
    Verify route_geojson output is a valid GeoJSON LineString with [lon, lat] coordinates.
    """
    result = compute_evacuation_routes(handmade_scenario_state)
    route = result.routes["P1"]["S1"]
    assert route.status == "ok"
    assert route.route_geojson is not None
    assert route.route_geojson["type"] == "LineString"

    coords = route.route_geojson["coordinates"]
    assert len(coords) >= 2
    # Check [lon, lat] format (lon around 80.2, lat around 13.0)
    for lon, lat in coords:
        assert 80.0 <= lon <= 80.5
        assert 12.5 <= lat <= 13.5


def test_routing_cache_behavior(handmade_scenario_state: ScenarioState):
    """
    Verify results are cached per scenario state and identical inputs return cached object.
    """
    clear_evacuation_cache()
    state = handmade_scenario_state.copy()

    # First call computes and caches
    res1 = compute_evacuation_routes(state, use_cache=True)
    # Second call retrieves from cache
    res2 = compute_evacuation_routes(state, use_cache=True)
    assert res1 is res2

    # Modifying state conditions changes cache key
    state.failed_shelters.add("S1")
    res3 = compute_evacuation_routes(state, use_cache=True)
    assert res3 is not res1
    assert res3.routes["P1"]["S1"].status == "no_route"


def test_failed_shelters_are_unavailable(handmade_scenario_state: ScenarioState):
    """
    Verify shelters in failed_shelters are marked no_route with infinite cost.
    """
    state = handmade_scenario_state.copy()
    state.failed_shelters.add("S1")

    result = compute_evacuation_routes(state)
    route_s1 = result.routes["P1"]["S1"]
    assert route_s1.status == "no_route"
    assert math.isinf(route_s1.cost)

    # S2 remains reachable
    route_s2 = result.routes["P1"]["S2"]
    assert route_s2.status == "ok"
