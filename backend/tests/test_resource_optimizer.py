from __future__ import annotations

import pytest

from app.models.schemas import OptimizationResult
from app.simulation.evacuation import clear_evacuation_cache
from app.simulation.resource_optimizer import (
    DEFAULT_OPTIMIZER_CONFIG,
    largest_remainder_distribution,
    optimize_resources,
)
from app.simulation.scenario import ScenarioState


# ==============================================================================
# SECTION 10 REQUIRED TESTS: ITEMS 5, 6, 7, 9, 12, 13, 14
# ==============================================================================


def test_item_5_shelter_capacity_never_exceeded(
    handmade_scenario_state: ScenarioState, real_scenario_state: ScenarioState
):
    """
    Section 10, Test 5:
    'Total people assigned to a shelter never exceed its capacity.'
    Tested on both handmade fixture and real data.
    """
    clear_evacuation_cache()

    # 1. On handmade fixture
    hm_result = optimize_resources(handmade_scenario_state)
    for shelter in handmade_scenario_state.shelters:
        assigned_to_s = sum(
            sa.people
            for z in hm_result.zones
            for sa in z.shelter_assignments
            if sa.shelter_id == shelter.id
        )
        assert assigned_to_s <= shelter.capacity

    # 2. On real data
    real_result = optimize_resources(real_scenario_state)
    for shelter in real_scenario_state.shelters:
        assigned_to_s = sum(
            sa.people
            for z in real_result.zones
            for sa in z.shelter_assignments
            if sa.shelter_id == shelter.id
        )
        assert assigned_to_s <= shelter.capacity


def test_item_6_filling_or_failing_shelter_reassigns_or_unmet(
    handmade_scenario_state: ScenarioState,
):
    """
    Section 10, Test 6:
    'Filling or failing a shelter reassigns people to other shelters, or reports them as unmet.'
    Tested on the handmade fixture (Shelter S1 cap=400, Shelter S2 cap=300).
    """
    clear_evacuation_cache()
    # Baseline run
    base_res = optimize_resources(handmade_scenario_state)
    assert base_res.totals.total_assigned_to_shelters > 0

    # 1. Fail Shelter S1: mark S1 as failed
    state_failed = handmade_scenario_state.copy()
    state_failed.failed_shelters.add("S1")
    failed_res = optimize_resources(state_failed)

    # No one can be assigned to S1
    s1_people = sum(
        sa.people
        for z in failed_res.zones
        for sa in z.shelter_assignments
        if sa.shelter_id == "S1"
    )
    assert s1_people == 0

    # S2 can receive at most its capacity (300)
    s2_people = sum(
        sa.people
        for z in failed_res.zones
        for sa in z.shelter_assignments
        if sa.shelter_id == "S2"
    )
    assert s2_people <= 300
    # Any remainder from P1 (600 affected) must be reported as unmet
    assert failed_res.totals.total_unmet_people > 0

    # 2. Fill Shelter S1 (capacity set to 0)
    state_filled = handmade_scenario_state.copy()
    for s in state_filled.shelters:
        if s.id == "S1":
            s.capacity = 0
    filled_res = optimize_resources(state_filled)

    s1_filled_people = sum(
        sa.people
        for z in filled_res.zones
        for sa in z.shelter_assignments
        if sa.shelter_id == "S1"
    )
    assert s1_filled_people == 0
    assert filled_res.totals.total_unmet_people > 0


def test_item_7_reducing_rescue_teams_leaves_unserved(
    handmade_scenario_state: ScenarioState, real_scenario_state: ScenarioState
):
    """
    Section 10, Test 7:
    'Reducing rescue teams from 3 to 1 leaves only one zone served and the others reported as unserved.'
    """
    clear_evacuation_cache()

    # 1. On handmade fixture
    st_hm = handmade_scenario_state.copy()
    st_hm.resources.rescue_teams = 1
    res_hm = optimize_resources(st_hm)

    served_teams = [z for z in res_hm.zones if z.rescue_team]
    unserved_teams = [z for z in res_hm.zones if not z.rescue_team]
    assert len(served_teams) == 1
    assert len(unserved_teams) == len(res_hm.zones) - 1
    assert res_hm.totals.resource_utilisation.rescue_teams_used == 1

    # 2. On real data at severity 1.0
    st_real = real_scenario_state.copy()
    st_real.resources.rescue_teams = 1
    res_real = optimize_resources(st_real)

    served_real = [z for z in res_real.zones if z.rescue_team]
    unserved_real = [z for z in res_real.zones if not z.rescue_team]
    assert len(served_real) == 1
    assert len(unserved_real) == 5
    assert res_real.totals.resource_utilisation.rescue_teams_used == 1


def test_item_9_supply_totals_equal_inputs_exactly(
    handmade_scenario_state: ScenarioState, real_scenario_state: ScenarioState
):
    """
    Section 10, Test 9:
    'Supply totals equal the inputs exactly (food packets and medical kits).'
    Tests largest-remainder rounding guarantees exact conservation of supply items.
    """
    clear_evacuation_cache()

    # Test with standard totals
    res_hm = optimize_resources(handmade_scenario_state)
    assert (
        sum(z.food_packets for z in res_hm.zones)
        == handmade_scenario_state.resources.food_packets
    )
    assert (
        sum(z.medical_kits for z in res_hm.zones)
        == handmade_scenario_state.resources.medical_kits
    )

    # Test with arbitrary odd totals (e.g. 503 food packets, 97 medical kits)
    st_odd = handmade_scenario_state.copy()
    st_odd.resources.food_packets = 503
    st_odd.resources.medical_kits = 97
    res_odd = optimize_resources(st_odd)

    assert sum(z.food_packets for z in res_odd.zones) == 503
    assert sum(z.medical_kits for z in res_odd.zones) == 97

    # Unit test largest_remainder_distribution directly
    weights = {"A": 10.3, "B": 20.7, "C": 5.1}
    distributed = largest_remainder_distribution(100, weights)
    assert sum(distributed.values()) == 100


def test_item_12_cutoff_zone_gets_boat_or_unmet_if_exhausted(
    real_scenario_state: ScenarioState,
):
    """
    Section 10, Test 12:
    'A zone cut off by impassable roads gets a boat if boats remain;
     if boats run out it is reported as unmet.'
    Tested on real data at severity 1.25 where P1 and P2 are cut off.
    """
    clear_evacuation_cache()
    state = real_scenario_state.copy()
    state.severity = 1.25

    # 1. With 2 boats available: both P1 and P2 get a boat
    state.resources.boats = 2
    res_2 = optimize_resources(state)
    p1 = next(z for z in res_2.zones if z.zone_id == "P1")
    p2 = next(z for z in res_2.zones if z.zone_id == "P2")
    assert p1.rescued_by_boat > 0
    assert p2.rescued_by_boat > 0
    assert res_2.totals.resource_utilisation.boats_used == 2

    # 2. With 1 boat available: only the higher priority cut-off zone (P2) gets a boat;
    # P1 runs out of boats and is reported as unmet
    state.resources.boats = 1
    res_1 = optimize_resources(state)
    p1_res1 = next(z for z in res_1.zones if z.zone_id == "P1")
    p2_res1 = next(z for z in res_1.zones if z.zone_id == "P2")
    assert p2_res1.rescued_by_boat > 0
    assert p1_res1.rescued_by_boat == 0
    assert p1_res1.unmet_people == p1_res1.affected_people
    assert res_1.totals.resource_utilisation.boats_used == 1

    # 3. With 0 boats: both cut-off zones have 0 rescued by boat and 100% unmet
    state.resources.boats = 0
    res_0 = optimize_resources(state)
    p1_res0 = next(z for z in res_0.zones if z.zone_id == "P1")
    p2_res0 = next(z for z in res_0.zones if z.zone_id == "P2")
    assert p1_res0.rescued_by_boat == 0
    assert p2_res0.rescued_by_boat == 0
    assert p1_res0.unmet_people == p1_res0.affected_people
    assert p2_res0.unmet_people == p2_res0.affected_people


def test_item_13_boat_rescues_at_most_boat_capacity(
    real_scenario_state: ScenarioState,
):
    """
    Section 10, Test 13:
    'A boat never rescues more than BOAT_CAPACITY people from a zone; the remainder is unmet.'
    Tested at severity 1.25 where P1 has 1800 affected and P2 has 2133 affected.
    """
    clear_evacuation_cache()
    state = real_scenario_state.copy()
    state.severity = 1.25
    state.resources.boats = 2

    capacity = DEFAULT_OPTIMIZER_CONFIG["boat_capacity"]  # 400
    res = optimize_resources(state)

    p1 = next(z for z in res.zones if z.zone_id == "P1")
    p2 = next(z for z in res.zones if z.zone_id == "P2")

    # Boat rescues at most BOAT_CAPACITY (400)
    assert p1.rescued_by_boat == capacity
    assert p2.rescued_by_boat == capacity

    # Remainder is reported as unmet
    assert p1.unmet_people == p1.affected_people - capacity
    assert p2.unmet_people == p2.affected_people - capacity


def test_item_14_at_severity_1_no_boat_used(
    real_scenario_state: ScenarioState,
):
    """
    Section 10, Test 14:
    'At severity 1.0 (no zone cut off) no boat is used.'
    """
    clear_evacuation_cache()
    state = real_scenario_state.copy()
    state.severity = 1.0
    state.resources.boats = 2

    res = optimize_resources(state)

    # No boat used because all zones have reachable road routes to shelters
    assert res.totals.total_rescued_by_boat == 0
    assert res.totals.resource_utilisation.boats_used == 0
    for z in res.zones:
        assert z.rescued_by_boat == 0
