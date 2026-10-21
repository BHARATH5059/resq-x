from __future__ import annotations

import math
import pytest
from app.simulation.risk_engine import (
    DEFAULT_RISK_CONFIG,
    calculate_all_edges_risk,
    calculate_all_zones_risk,
    calculate_edge_risk,
    calculate_zone_risk,
    classify_risk_level,
    run_risk_engine,
)
from app.simulation.scenario import ScenarioState


# ==============================================================================
# SECTION 10 BEHAVIOUR TESTS
# ==============================================================================


def test_behaviour_1_higher_severity_increases_risk_and_affected(
    handmade_scenario_state: ScenarioState,
):
    """
    Section 10, Test 1:
    'Higher severity gives higher risk scores and more affected people.'
    """
    state_low = handmade_scenario_state.copy()
    state_low.severity = 0.5
    result_low = run_risk_engine(state_low)

    state_med = handmade_scenario_state.copy()
    state_med.severity = 1.0
    result_med = run_risk_engine(state_med)

    state_high = handmade_scenario_state.copy()
    state_high.severity = 1.5
    result_high = run_risk_engine(state_high)

    p1_low = next(z for z in result_low.zones if z.zone_id == "P1")
    p1_med = next(z for z in result_med.zones if z.zone_id == "P1")
    p1_high = next(z for z in result_high.zones if z.zone_id == "P1")

    # Depth increases with severity
    assert p1_low.depth < p1_med.depth < p1_high.depth
    assert pytest.approx(p1_low.depth) == 0.45
    assert pytest.approx(p1_med.depth) == 0.90
    assert pytest.approx(p1_high.depth) == 1.35

    # Risk scores increase with severity
    assert p1_low.risk_score < p1_med.risk_score < p1_high.risk_score
    assert pytest.approx(p1_low.risk_score) == 0.49
    assert pytest.approx(p1_med.risk_score) == 0.64
    assert pytest.approx(p1_high.risk_score) == 0.79

    # Affected people increase with severity
    assert p1_low.affected_people < p1_med.affected_people < p1_high.affected_people
    assert p1_low.affected_people == 300
    assert p1_med.affected_people == 600
    assert p1_high.affected_people == 900

    # Total affected across the scenario also increases
    assert (
        result_low.total_affected_people
        < result_med.total_affected_people
        < result_high.total_affected_people
    )


def test_behaviour_2_outside_zone_zero_depth_and_zero_affected(
    handmade_scenario_state: ScenarioState, real_scenario_state: ScenarioState
):
    """
    Section 10, Test 2:
    'A zone outside every flood polygon has depth 0 and no affected people.'
    """
    # 1. On handmade fixture: Zone P2 is intentionally placed outside flood polygon F1
    res_handmade = run_risk_engine(handmade_scenario_state)
    p2_hm = next(z for z in res_handmade.zones if z.zone_id == "P2")

    assert p2_hm.depth == 0.0
    assert p2_hm.depth_norm == 0.0
    assert p2_hm.affected_people == 0
    assert p2_hm.priority == 0.0

    # Even at extreme severity, outside zone remains at depth 0 and 0 affected people
    hm_extreme = handmade_scenario_state.copy()
    hm_extreme.severity = 3.0
    res_extreme = run_risk_engine(hm_extreme)
    p2_extreme = next(z for z in res_extreme.zones if z.zone_id == "P2")
    assert p2_extreme.depth == 0.0
    assert p2_extreme.affected_people == 0

    # 2. On real Chennai data: P5 (West Layout) and P6 (North-East Market Area) are outside flood polygons
    res_real = run_risk_engine(real_scenario_state)
    p5 = next(z for z in res_real.zones if z.zone_id == "P5")
    p6 = next(z for z in res_real.zones if z.zone_id == "P6")

    assert p5.depth == 0.0
    assert p5.affected_people == 0
    assert p5.priority == 0.0

    assert p6.depth == 0.0
    assert p6.affected_people == 0
    assert p6.priority == 0.0


def test_behaviour_8_increasing_risk_raises_priority(
    handmade_scenario_state: ScenarioState,
):
    """
    Section 10, Test 8 (Module 1 part):
    'Increasing risk in one zone raises its priority...'
    """
    state1 = handmade_scenario_state.copy()
    state1.severity = 0.8
    res1 = run_risk_engine(state1)
    p1_s1 = next(z for z in res1.zones if z.zone_id == "P1")

    state2 = handmade_scenario_state.copy()
    state2.severity = 1.4
    res2 = run_risk_engine(state2)
    p1_s2 = next(z for z in res2.zones if z.zone_id == "P1")

    # Priority = risk_score * affected_people
    assert p1_s2.risk_score > p1_s1.risk_score
    assert p1_s2.affected_people > p1_s1.affected_people
    assert p1_s2.priority > p1_s1.priority


# ==============================================================================
# HAND-MADE FIXTURE EXACT VALUE TESTS
# ==============================================================================


def test_handmade_fixture_exact_hand_calculated_values(
    handmade_scenario_state: ScenarioState, handmade_expected_values: dict
):
    """
    Verify all calculated values on the handmade fixture match the exact hand calculations.
    """
    expected_1_0 = handmade_expected_values["severity_1_0"]
    result_1_0 = run_risk_engine(handmade_scenario_state)

    for zone_id in ["P1", "P2"]:
        z_res = next(z for z in result_1_0.zones if z.zone_id == zone_id)
        exp = expected_1_0[zone_id]

        assert pytest.approx(z_res.depth, rel=1e-5) == exp["depth"]
        assert pytest.approx(z_res.depth_norm, rel=1e-5) == exp["depth_norm"]
        assert pytest.approx(z_res.pop_norm, rel=1e-5) == exp["pop_norm"]
        assert (
            pytest.approx(z_res.vulnerable_share_norm, rel=1e-5)
            == exp["vulnerable_share_norm"]
        )
        assert pytest.approx(z_res.risk_score, rel=1e-5) == exp["risk_score"]
        assert z_res.risk_level == exp["risk_level"]
        assert z_res.affected_people == exp["affected_people"]
        assert pytest.approx(z_res.priority, rel=1e-5) == exp["priority"]

    # Verify edge risk for edge (1, 2) which is flooded (depth 0.9)
    edge_risks = calculate_all_edges_risk(
        handmade_scenario_state.graph,
        handmade_scenario_state.flood_polygons,
        severity=1.0,
    )
    e12 = edge_risks[(1, 2)]
    exp_e12 = expected_1_0["edge_1_2"]
    assert pytest.approx(e12.edge_depth) == exp_e12["edge_depth"]
    assert e12.impassable == exp_e12["impassable"]
    assert pytest.approx(e12.edge_cost) == exp_e12["edge_cost"]

    # Verify bridge edge (2, 4) which is dry
    e_bridge = edge_risks[(2, 4)]
    exp_bridge = expected_1_0["edge_bridge"]
    assert pytest.approx(e_bridge.edge_depth, abs=1e-5) == exp_bridge["edge_depth"]
    assert e_bridge.impassable == exp_bridge["impassable"]
    assert pytest.approx(e_bridge.edge_cost) == exp_bridge["edge_cost"]


def test_handmade_fixture_impassable_threshold(
    handmade_scenario_state: ScenarioState, handmade_expected_values: dict
):
    """
    Verify edge becomes impassable (depth >= 1.0) when severity increases.
    """
    state_1_5 = handmade_scenario_state.copy()
    state_1_5.severity = 1.5

    result_1_5 = run_risk_engine(state_1_5)
    p1 = next(z for z in result_1_5.zones if z.zone_id == "P1")
    exp_p1 = handmade_expected_values["severity_1_5"]["P1"]

    assert pytest.approx(p1.depth) == exp_p1["depth"]
    assert pytest.approx(p1.risk_score) == exp_p1["risk_score"]
    assert p1.risk_level == exp_p1["risk_level"]
    assert p1.affected_people == exp_p1["affected_people"]
    assert pytest.approx(p1.priority) == exp_p1["priority"]

    edge_risks = calculate_all_edges_risk(
        state_1_5.graph,
        state_1_5.flood_polygons,
        severity=1.5,
    )
    e12 = edge_risks[(1, 2)]
    assert e12.edge_depth >= 1.0
    assert e12.impassable is True
    assert math.isinf(e12.edge_cost)


# ==============================================================================
# FORMULAS & CLASSIFICATION UNIT TESTS
# ==============================================================================


@pytest.mark.parametrize(
    "score,expected_level",
    [
        (0.0, "low"),
        (0.249, "low"),
        (0.25, "medium"),
        (0.499, "medium"),
        (0.50, "high"),
        (0.749, "high"),
        (0.75, "critical"),
        (1.0, "critical"),
    ],
)
def test_classify_risk_level_boundaries(score: float, expected_level: str):
    """
    Verify risk level classification:
    below 0.25 low, below 0.5 medium, below 0.75 high, otherwise critical.
    """
    assert classify_risk_level(score) == expected_level


def test_edge_cost_formula():
    """
    Formula: edge_cost = length * (1 + 5 * min(edge_depth / 1.0, 1.0)) when depth < 1.0
    impassable when depth >= 1.0
    """
    from app.simulation.risk_engine import calculate_edge_risk
    from shapely.geometry import Polygon
    from app.simulation.scenario import FloodPolygon
    import networkx as nx

    G = nx.DiGraph()
    G.add_node(10, x=80.0, y=13.0)
    G.add_node(11, x=80.1, y=13.0)
    G.add_edge(10, 11, length=200.0)

    # 1. Dry edge (depth = 0)
    risk_dry = calculate_edge_risk(10, 11, G[10][11], G, flood_polygons=[], severity=1.0)
    assert risk_dry.edge_depth == 0.0
    assert risk_dry.impassable is False
    assert risk_dry.edge_cost == 200.0

    # 2. Shallow flood (depth = 0.4) -> cost = 200 * (1 + 5 * 0.4) = 200 * 3.0 = 600.0
    f_shallow = [
        FloodPolygon(
            id="F_shallow",
            name="Shallow",
            depth_m=0.4,
            geometry=Polygon([[79.9, 12.9], [80.2, 12.9], [80.2, 13.1], [79.9, 13.1], [79.9, 12.9]]),
        )
    ]
    risk_shallow = calculate_edge_risk(10, 11, G[10][11], G, flood_polygons=f_shallow, severity=1.0)
    assert pytest.approx(risk_shallow.edge_depth) == 0.4
    assert risk_shallow.impassable is False
    assert pytest.approx(risk_shallow.edge_cost) == 600.0

    # 3. Impassable flood (depth = 1.0) -> cost = inf, impassable = True
    f_deep = [
        FloodPolygon(
            id="F_deep",
            name="Deep",
            depth_m=1.0,
            geometry=Polygon([[79.9, 12.9], [80.2, 12.9], [80.2, 13.1], [79.9, 13.1], [79.9, 12.9]]),
        )
    ]
    risk_deep = calculate_edge_risk(10, 11, G[10][11], G, flood_polygons=f_deep, severity=1.0)
    assert risk_deep.edge_depth >= 1.0
    assert risk_deep.impassable is True
    assert math.isinf(risk_deep.edge_cost)


def test_config_weights_and_thresholds_override(handmade_scenario_state: ScenarioState):
    """
    Verify weights and thresholds are not hardcoded inside functions
    and custom config overrides alter the calculation as specified.
    """
    custom_config = {
        "weight_depth": 0.8,
        "weight_vulnerable": 0.1,
        "weight_population": 0.1,
        "depth_norm_max": 2.0,
    }

    result_default = run_risk_engine(handmade_scenario_state)
    result_custom = run_risk_engine(handmade_scenario_state, config=custom_config)

    p1_def = next(z for z in result_default.zones if z.zone_id == "P1")
    p1_cust = next(z for z in result_custom.zones if z.zone_id == "P1")

    # With depth_norm_max = 2.0, depth 0.9 gives depth_norm = 0.45 instead of 0.60
    assert pytest.approx(p1_cust.depth_norm) == 0.45
    # Risk score will differ based on overridden weights
    assert p1_def.risk_score != p1_cust.risk_score


# ==============================================================================
# REAL DATA INTEGRATION TESTS
# ==============================================================================


def test_real_data_scenario_state_structure(real_scenario_state: ScenarioState):
    """
    Verify real data is loaded accurately from data/ without modifications.
    """
    assert len(real_scenario_state.zones) == 6
    assert len(real_scenario_state.shelters) == 6
    assert len(real_scenario_state.hospitals) == 4
    assert len(real_scenario_state.bridges) == 3
    assert len(real_scenario_state.flood_polygons) == 4
    assert len(real_scenario_state.graph.nodes) == 1266
    assert len(real_scenario_state.graph.edges) > 2000

    # Verify bridge edges exist in the DiGraph
    for b in real_scenario_state.bridges:
        for u, v in b.edges:
            assert real_scenario_state.graph.has_edge(u, v)


def test_real_data_risk_engine_run(real_scenario_state: ScenarioState):
    """
    Verify risk engine runs correctly on real Chennai road network and flood polygons.
    """
    result = run_risk_engine(real_scenario_state)

    assert result.severity == 1.0
    assert len(result.zones) == 6
    assert result.total_affected_people > 0
    assert result.impassable_edge_count > 0

    # Zones P1, P2, P3, P4 should have positive depth; P5, P6 are 0
    zones_by_id = {z.zone_id: z for z in result.zones}
    assert zones_by_id["P1"].depth == 1.2
    assert zones_by_id["P2"].depth == 0.8
    assert zones_by_id["P3"].depth == 0.5
    assert zones_by_id["P4"].depth == 0.3
    assert zones_by_id["P5"].depth == 0.0
    assert zones_by_id["P6"].depth == 0.0

    # Impassable edges exist where flood depth >= 1.0 (F1 depth is 1.2)
    assert result.impassable_edge_count > 100


def test_scenario_state_reset_and_failure_tracking(handmade_scenario_state: ScenarioState):
    """
    Verify failure tracking and reset behavior in ScenarioState.
    """
    state = handmade_scenario_state.copy()
    assert len(state.failed_shelters) == 0
    assert len(state.blocked_edges) == 0

    state.severity = 1.8
    state.failed_shelters.add("S1")
    state.failed_bridges.add("B1")
    state.blocked_edges.add((1, 2))

    assert len(state.failed_shelters) == 1
    assert len(state.failed_bridges) == 1
    assert len(state.blocked_edges) == 1

    state.clear_failures()
    assert len(state.failed_shelters) == 0
    assert len(state.failed_bridges) == 0
    assert len(state.blocked_edges) == 0
    assert state.severity == 1.8  # clear_failures preserves severity

    state.reset()
    assert state.severity == 1.0  # reset returns severity to 1.0
