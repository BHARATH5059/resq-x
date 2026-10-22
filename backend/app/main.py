from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import get_scenario_state, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler to initialize ScenarioState and baseline at startup."""
    get_scenario_state()
    yield


app = FastAPI(
    title="RESQ-X Disaster Response Simulation API",
    description="Real-time disaster evacuation routing and resource allocation engine.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend Vite dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
