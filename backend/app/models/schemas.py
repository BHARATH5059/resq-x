from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BaseAccessibleModel(BaseModel):
    """Base model that allows both attribute and dict-like key access."""

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class Zone(BaseAccessibleModel):
    id: str
    name: str
    lat: float
    lon: float
    population: int
    vulnerable_share: float
    node: int
    snap_m: float = 0.0


class Shelter(BaseAccessibleModel):
    id: str
    name: str
    lat: float
    lon: float
    capacity: int
    node: int
    snap_m: float = 0.0


class Hospital(BaseAccessibleModel):
    id: str
    name: str
    lat: float
    lon: float
    beds_available: int
    node: int
    snap_m: float = 0.0


class Bridge(BaseAccessibleModel):
    id: str
    name: str
    edges: List[List[int]]


class ResourceBase(BaseAccessibleModel):
    name: str
    lat: float
    lon: float
    node: int


class Resources(BaseAccessibleModel):
    base: ResourceBase
    rescue_teams: int
    ambulances: int
    boats: int
    food_packets: int
    medical_kits: int


class FloodZoneFeature(BaseAccessibleModel):
    id: str
    name: str
    depth_m: float
    simulated: bool = True
    geometry: Any = None  # Shapely shape or GeoJSON geometry


class ZoneRisk(BaseAccessibleModel):
    zone_id: str
    name: str
    depth: float
    depth_norm: float
    pop_norm: float
    vulnerable_share_norm: float
    risk_score: float
    risk_level: str
    affected_people: int
    priority: float
    population: int
    vulnerable_share: float
    lat: float
    lon: float
    node: int


class EdgeRisk(BaseAccessibleModel):
    u: int
    v: int
    length: float
    edge_depth: float
    edge_cost: float
    impassable: bool


class RiskAssessmentResult(BaseAccessibleModel):
    severity: float
    zones: List[ZoneRisk]
    total_affected_people: int
    impassable_edge_count: int


class RouteDetail(BaseAccessibleModel):
    status: str = "ok"  # "ok" or "no_route"
    cost: float
    length: float
    path: List[int]
    route_geojson: Optional[Dict[str, Any]] = None
    flooded_edges_count: int = 0
    max_flood_depth: float = 0.0


class ZoneShelterRoute(BaseAccessibleModel):
    zone_id: str
    shelter_id: str
    status: str = "ok"  # "ok" or "no_route"
    cost: float
    length: float
    path: List[int]
    route_geojson: Optional[Dict[str, Any]] = None
    flooded_edges_count: int = 0
    max_flood_depth: float = 0.0
    baseline_route: Optional[RouteDetail] = None


class EvacuationRoutingResult(BaseAccessibleModel):
    severity: float
    routes: Dict[str, Dict[str, ZoneShelterRoute]]
    unreachable_pairs_count: int
    differing_routes_count: int
    cut_off_zones: List[str]
    total_unmet_people: int = 0


class ShelterAssignment(BaseAccessibleModel):
    shelter_id: str
    shelter_name: str
    people: int
    route_cost: float
    route_length: float


class ZoneOptimizationResult(BaseAccessibleModel):
    zone_id: str
    name: str
    risk_level: str
    affected_people: int
    shelter_assignments: List[ShelterAssignment]
    assigned_to_shelters: int
    rescued_by_boat: int
    unmet_people: int
    rescue_team: bool
    ambulance: bool
    hospital_id: Optional[str] = None
    hospital_name: Optional[str] = None
    food_packets: int
    medical_kits: int


class ResourceUtilisation(BaseAccessibleModel):
    rescue_teams_used: int
    rescue_teams_available: int
    ambulances_used: int
    ambulances_available: int
    boats_used: int
    boats_available: int
    food_packets_distributed: int
    food_packets_available: int
    medical_kits_distributed: int
    medical_kits_available: int


class OptimizationTotals(BaseAccessibleModel):
    total_affected_people: int
    total_assigned_to_shelters: int
    total_rescued_by_boat: int
    total_unmet_people: int
    total_travel_cost: float
    resource_utilisation: ResourceUtilisation


class OptimizationResult(BaseAccessibleModel):
    zones: List[ZoneOptimizationResult]
    totals: OptimizationTotals


class MetricBeforeAfter(BaseAccessibleModel):
    before: float
    after: float
    delta: float


class TotalsDiff(BaseAccessibleModel):
    people_assigned: MetricBeforeAfter
    rescued_by_boat: MetricBeforeAfter
    unmet: MetricBeforeAfter
    total_travel_cost: MetricBeforeAfter


class ZoneDiff(BaseAccessibleModel):
    zone_id: str
    zone_name: str
    route_changed: bool
    old_route_length: Optional[float] = None
    new_route_length: Optional[float] = None
    old_assigned_shelters: List[Dict[str, Any]] = Field(default_factory=list)
    new_assigned_shelters: List[Dict[str, Any]] = Field(default_factory=list)
    old_unmet: int
    new_unmet: int


class TeamMovement(BaseAccessibleModel):
    zone_id: str
    before: bool
    after: bool
    action: str


class AmbulanceMovement(BaseAccessibleModel):
    zone_id: str
    before_ambulance: bool
    after_ambulance: bool
    before_hospital_id: Optional[str] = None
    before_hospital_name: Optional[str] = None
    after_hospital_id: Optional[str] = None
    after_hospital_name: Optional[str] = None
    action: str


class SupplyMovement(BaseAccessibleModel):
    zone_id: str
    food_packets_before: int
    food_packets_after: int
    food_packets_delta: int
    medical_kits_before: int
    medical_kits_after: int
    medical_kits_delta: int


class ResourceMovements(BaseAccessibleModel):
    teams: List[TeamMovement] = Field(default_factory=list)
    ambulances: List[AmbulanceMovement] = Field(default_factory=list)
    supplies: List[SupplyMovement] = Field(default_factory=list)


class SimulationPlan(BaseAccessibleModel):
    severity: float
    risk: RiskAssessmentResult
    routes: EvacuationRoutingResult
    allocation: OptimizationResult
    unmet: int
    totals: OptimizationTotals


class SimulationDiff(BaseAccessibleModel):
    event_type: str
    event_id: Optional[str] = None
    event_details: Dict[str, Any] = Field(default_factory=dict)
    zones: Dict[str, ZoneDiff]
    totals: TotalsDiff
    resource_movements: ResourceMovements
    messages: List[str]
    plan: Optional[SimulationPlan] = None


class FailureEventRequest(BaseAccessibleModel):
    type: str
    id: Optional[str] = None
    edge: Optional[List[int]] = None
    amount: Optional[int] = None
    field: Optional[str] = None


class FailureResponse(BaseAccessibleModel):
    plan: SimulationPlan
    diff: SimulationDiff

