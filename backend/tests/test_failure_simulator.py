from __future__ import annotations

import pytest

from app.models.schemas import FailureEventRequest, SimulationDiff, SimulationPlan
from app.simulation.failure_simulator import (
    apply_failure,
    block_bridge,
    block_edge,
    fail_hospital,
    fail_shelter,
    fill_shelter,
    reduce_resources,
    reset,
    run_simulation,
)
from app.simulation.scenario import ScenarioState


# =====================================================================
# 1. Hand-made fixture tests (Section 10 items with exact checks)
# =====================================================================

def test_handmade_simulate_baseline(handmade_scenario_state: ScenarioState):
    """Verify baseline simulation on handmade fixture produces valid plan and saves as baseline."""
    plan = run_simulation(handmade_scenario_state, save_as_baseline=True)

    assert isinstance(plan, SimulationPlan)
    assert plan.severity == 1.0
    assert plan.totals.total_affected_people == 600
    assert plan.totals.total_assigned_to_shelters == 600
    assert plan.totals.total_unmet_people == 0
    assert handmade_scenario_state.baseline is plan


def test_handmade_block_bridge(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Blocking Bridge B1 removes edges (2, 4) & (4, 2).
    Zone P1 evacuees reroute around the bridge to reach S2, increasing route length from 583.33m to 740m.
    """
    diff = block_bridge(handmade_scenario_state, "B1")

    assert isinstance(diff, SimulationDiff)
    assert "B1" in handmade_scenario_state.failed_bridges
    assert (2, 4) in handmade_scenario_state.blocked_edges
    assert (4, 2) in handmade_scenario_state.blocked_edges

    p1_diff = diff.zones["P1"]
    assert p1_diff.route_changed is True
    assert p1_diff.old_route_length == pytest.approx(583.33, abs=0.1)
    assert p1_diff.new_route_length == pytest.approx(740.0, abs=0.1)
    assert any("Bridge B1" in msg for msg in diff.messages)


def test_handmade_block_edge(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Blocking edge [3, 5] cuts off Shelter S1 at node 5.
    Evacuees can no longer access S1, so P1's evacuees can only reach S2 (capacity 300),
    causing unmet evacuees to rise to 300.
    """
    diff = block_edge(handmade_scenario_state, [3, 5])

    assert isinstance(diff, SimulationDiff)
    assert (3, 5) in handmade_scenario_state.blocked_edges

    p1_diff = diff.zones["P1"]
    assert p1_diff.route_changed is True
    assert not any(sa["shelter_id"] == "S1" for sa in p1_diff.new_assigned_shelters)
    assert p1_diff.new_unmet == 300
    assert diff.totals.unmet.delta == 300.0


def test_handmade_fail_shelter(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Failing shelter S1 marks it unavailable.
    All evacuees can only go to S2 (capacity 300), leaving 300 unmet.
    """
    diff = fail_shelter(handmade_scenario_state, "S1")

    assert isinstance(diff, SimulationDiff)
    assert "S1" in handmade_scenario_state.failed_shelters

    p1_diff = diff.zones["P1"]
    assert p1_diff.route_changed is True
    assert not any(sa["shelter_id"] == "S1" for sa in p1_diff.new_assigned_shelters)
    assert p1_diff.new_unmet == 300
    assert diff.totals.people_assigned.delta == -300.0
    assert diff.totals.unmet.delta == 300.0


def test_handmade_fill_shelter(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Filling shelter S1 sets its capacity to 0.
    Evacuees reallocate to S2 (up to 300), leaving 300 unmet.
    """
    diff = fill_shelter(handmade_scenario_state, "S1")

    s1 = next(s for s in handmade_scenario_state.shelters if s.id == "S1")
    assert s1.capacity == 0

    p1_diff = diff.zones["P1"]
    assert p1_diff.route_changed is True
    assert not any(sa["shelter_id"] == "S1" for sa in p1_diff.new_assigned_shelters)
    assert p1_diff.new_unmet == 300
    assert diff.totals.unmet.delta == 300.0


def test_handmade_fail_hospital(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Failing hospital H1 forces Zone P1's ambulance to reroute to H2.
    """
    diff = fail_hospital(handmade_scenario_state, "H1")

    assert isinstance(diff, SimulationDiff)
    assert "H1" in handmade_scenario_state.failed_hospitals

    amb_movements = diff.resource_movements.ambulances
    assert len(amb_movements) == 1
    mv = amb_movements[0]
    assert mv.zone_id == "P1"
    assert mv.before_hospital_id == "H1"
    assert mv.after_hospital_id == "H2"
    assert mv.action == "rerouted"


def test_handmade_reduce_resources(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Reducing rescue_teams from 3 to 0 leaves Zone P1 unserved.
    """
    diff = reduce_resources(handmade_scenario_state, "rescue_teams", 0)

    assert handmade_scenario_state.resources.rescue_teams == 0
    team_movements = diff.resource_movements.teams
    assert len(team_movements) == 1
    mv = team_movements[0]
    assert mv.zone_id == "P1"
    assert mv.before is True
    assert mv.after is False
    assert mv.action == "removed"


def test_handmade_reset_restores_baseline(handmade_scenario_state: ScenarioState):
    """
    Exact check on handmade fixture:
    Cumulative failures (block B1, fill S1, reduce rescue teams to 0)
    followed by reset restores the baseline plan exactly.
    """
    block_bridge(handmade_scenario_state, "B1")
    fill_shelter(handmade_scenario_state, "S1")
    reduce_resources(handmade_scenario_state, "rescue_teams", 0)

    assert len(handmade_scenario_state.failed_bridges) > 0
    assert next(s for s in handmade_scenario_state.shelters if s.id == "S1").capacity == 0
    assert handmade_scenario_state.resources.rescue_teams == 0

    diff_reset = reset(handmade_scenario_state)

    # Failures cleared
    assert len(handmade_scenario_state.failed_bridges) == 0
    assert len(handmade_scenario_state.failed_shelters) == 0
    assert len(handmade_scenario_state.failed_hospitals) == 0
    assert len(handmade_scenario_state.blocked_edges) == 0

    # Attributes restored
    assert next(s for s in handmade_scenario_state.shelters if s.id == "S1").capacity == 400
    assert handmade_scenario_state.resources.rescue_teams == 3

    # Diff against baseline shows zero differences
    assert diff_reset.totals.people_assigned.delta == 0.0
    assert diff_reset.totals.unmet.delta == 0.0
    assert diff_reset.totals.total_travel_cost.delta == 0.0
    for z in diff_reset.zones.values():
        assert z.route_changed is False
        assert z.new_unmet == z.old_unmet


def test_handmade_apply_failure_dispatcher(handmade_scenario_state: ScenarioState):
    """Verify apply_failure accepts both dict and FailureEventRequest models."""
    req = FailureEventRequest(type="block_bridge", id="B1")
    diff1 = apply_failure(handmade_scenario_state, req)
    assert "B1" in handmade_scenario_state.failed_bridges

    reset(handmade_scenario_state)

    diff2 = apply_failure(handmade_scenario_state, {"type": "fill_shelter", "id": "S1"})
    assert next(s for s in handmade_scenario_state.shelters if s.id == "S1").capacity == 0


# =====================================================================
# 2. Real-data tests at severity 1.0 (Required in user request)
# =====================================================================

def test_real_data_block_b1_changes_route(real_scenario_state: ScenarioState):
    """
    Real-data test:
    Blocking B1 changes at least one route.
    """
    real_scenario_state.severity = 1.0
    reset(real_scenario_state)
    diff = block_bridge(real_scenario_state, "B1")

    assert "B1" in real_scenario_state.failed_bridges
    assert any(z.route_changed for z in diff.zones.values()), "Blocking B1 must change at least one route"

    # Zone P2 routes across the bridge area in baseline; when B1 is blocked it reroutes
    assert diff.zones["P2"].route_changed is True
    assert diff.totals.total_travel_cost.delta > 0, "Rerouting around B1 must increase travel cost"
    reset(real_scenario_state)


def test_real_data_fill_s1_reassigns_people(real_scenario_state: ScenarioState):
    """
    Real-data test:
    Filling S1 (setting capacity to 0) reassigns its people or leaves them unmet.
    """
    real_scenario_state.severity = 1.0
    reset(real_scenario_state)
    diff = fill_shelter(real_scenario_state, "S1")

    # S1 capacity is set to 0
    s1 = next(s for s in real_scenario_state.shelters if s.id == "S1")
    assert s1.capacity == 0

    # No zone has S1 in its new assignments
    for z in diff.zones.values():
        assert not any(sa["shelter_id"] == "S1" for sa in z.new_assigned_shelters)

    # In baseline, S1 accommodated 1,000 evacuees. When filled, unmet increases
    assert diff.totals.unmet.after > 0
    assert diff.totals.people_assigned.after < diff.totals.people_assigned.before
    reset(real_scenario_state)


def test_real_data_reduce_rescue_teams_leaves_unserved(real_scenario_state: ScenarioState):
    """
    Real-data test:
    Reducing rescue teams from 3 to 1 leaves zones unserved.
    """
    real_scenario_state.severity = 1.0
    reset(real_scenario_state)
    diff = reduce_resources(real_scenario_state, "rescue_teams", 1)

    assert real_scenario_state.resources.rescue_teams == 1
    plan = diff.plan
    assert plan is not None
    assert plan.totals.resource_utilisation.rescue_teams_used == 1
    assert plan.totals.resource_utilisation.rescue_teams_available == 1

    # In baseline at 1.0, 3 zones (P1, P2, P3) had teams.
    # With 1 team, 2 zones must have their teams removed
    removed_teams = [m for m in diff.resource_movements.teams if m.action == "removed"]
    assert len(removed_teams) == 2
    reset(real_scenario_state)



def test_real_data_reset_restores_baseline_exactly(real_scenario_state: ScenarioState):
    """
    Real-data test:
    Cumulative failures (block B1, fill S1, reduce rescue teams to 1, fail H1)
    followed by reset restores the baseline exactly.
    """
    real_scenario_state.severity = 1.0
    ensure_baseline_plan = run_simulation(real_scenario_state, save_as_baseline=True)
    orig_assigned = ensure_baseline_plan.totals.total_assigned_to_shelters
    orig_unmet = ensure_baseline_plan.totals.total_unmet_people
    orig_cost = ensure_baseline_plan.totals.total_travel_cost

    # Apply cumulative failures
    block_bridge(real_scenario_state, "B1")
    fill_shelter(real_scenario_state, "S1")
    reduce_resources(real_scenario_state, "rescue_teams", 1)
    fail_hospital(real_scenario_state, "H1")

    # Verify cumulative failure state
    assert len(real_scenario_state.failed_bridges) == 1
    assert next(s for s in real_scenario_state.shelters if s.id == "S1").capacity == 0
    assert real_scenario_state.resources.rescue_teams == 1
    assert len(real_scenario_state.failed_hospitals) == 1

    # Reset
    diff = reset(real_scenario_state)

    # Assert failures cleared
    assert len(real_scenario_state.failed_bridges) == 0
    assert len(real_scenario_state.failed_shelters) == 0
    assert len(real_scenario_state.failed_hospitals) == 0
    assert len(real_scenario_state.blocked_edges) == 0

    # Assert shelter capacity and resources restored
    assert next(s for s in real_scenario_state.shelters if s.id == "S1").capacity == 1000
    assert real_scenario_state.resources.rescue_teams == 3

    # Assert plan matches baseline exactly
    assert diff.plan.totals.total_assigned_to_shelters == orig_assigned
    assert diff.plan.totals.total_unmet_people == orig_unmet
    assert diff.plan.totals.total_travel_cost == pytest.approx(orig_cost, rel=1e-5)
    assert diff.totals.people_assigned.delta == 0.0
    assert diff.totals.unmet.delta == 0.0
    assert diff.totals.total_travel_cost.delta == 0.0


def test_real_data_demo_sequence_sev_1_25(real_scenario_state: ScenarioState):
    """
    Demo sequence starting from severity 1.25:
    1. Baseline at 1.25 has boat rescues (P1, P2) and road evacuations (P3, P4).
    2. Block B1 -> routes reroute.
    3. Fill S1 -> capacity changes.
    4. Reduce teams to 1 -> only 1 team deployed.
    5. Fail hospital H1 -> P4's ambulance rerouted from H1 to H2.
    6. Reset -> restores 1.25 baseline exactly.
    """
    real_scenario_state.severity = 1.25
    base_plan = run_simulation(real_scenario_state, save_as_baseline=True)

    assert base_plan.totals.total_rescued_by_boat == 800

    # Step 1: Block B1
    diff1 = block_bridge(real_scenario_state, "B1")
    assert "B1" in real_scenario_state.failed_bridges

    # Step 2: Fill S1
    diff2 = fill_shelter(real_scenario_state, "S1")
    assert next(s for s in real_scenario_state.shelters if s.id == "S1").capacity == 0

    # Step 3: Reduce rescue teams to 1
    diff3 = reduce_resources(real_scenario_state, "rescue_teams", 1)
    assert real_scenario_state.resources.rescue_teams == 1

    # Step 4: Fail hospital H1
    diff4 = fail_hospital(real_scenario_state, "H1")
    # P4's ambulance in baseline was paired with H1; it should reroute to H2
    p4_amb = next((m for m in diff4.resource_movements.ambulances if m.zone_id == "P4"), None)
    assert p4_amb is not None
    assert p4_amb.before_hospital_id == "H1"
    assert p4_amb.after_hospital_id == "H2"
    assert p4_amb.action == "rerouted"

    # Step 5: Reset restores baseline
    diff_reset = reset(real_scenario_state)
    assert diff_reset.totals.total_travel_cost.delta == 0.0
    assert diff_reset.totals.unmet.delta == 0.0
    assert diff_reset.plan.totals.total_rescued_by_boat == 800
