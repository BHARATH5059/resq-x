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
