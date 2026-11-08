from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from psycopg2.pool import ThreadedConnectionPool

from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
from api.v1.dao.vehicle import ensure_vehicle_constraints
from api.v1.handler.vehicle import router as vehicle_router
from api.v1.handler.road_segment import router as road_segment_router
from api.v1.handler.location_ping import router as location_ping_router, vehicle_pings_router
from api.v1.handler.trip import router as trip_router, vehicle_trips_router
from api.v1.handler.vehicle_assignment import router as assignment_router

from api.v1.dao.parking_area import ParkingAreaCreate
from api.v1.handler.parking_area import ParkingAreaHandler

#------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ThreadedConnectionPool(
        POOL_CONFIG["minconn"],
        POOL_CONFIG["maxconn"],
        **PG_DB_CONFIG,
    )
    connection = pool.getconn()
    try:
        ensure_vehicle_constraints(connection)
    finally:
        pool.putconn(connection)

    app.state.pool = pool
    try:
        yield
    finally:
        pool.closeall()


app = FastAPI(
    title="MUU Vehicle API",
    description="Vehicle tracking API",
    lifespan=lifespan,
)


@app.get("/")
def api_info():
    return {
        "message": "MUU Vehicle API is running",
        "endpoints": {
            "vehicles": "/api/v1/vehicles",
            "parking_areas": "/api/v1/parking_areas",
            "health": "/health",
        },
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ==========================
# 5.3 Parking Area
# ==========================

@app.post("/api/v1/parking_areas")
async def create_parking_area(payload: ParkingAreaCreate, request: Request):
    return ParkingAreaHandler().create_parking_area(request, payload)

# Get a query of all parking areas or a filtered query
@app.get("/api/v1/parking_areas")
async def get_parking_areas(name: str | None = None, bbox: str | None = None, limit: int | None = None, offset: int | None = None):
    bbox_list = bbox.split(",") if bbox else None  # Converts the string into a list of floats

    if name is None and bbox is None and limit is None and offset is None:  # Runs if no filters are entered
        return ParkingAreaHandler().get_all_parking_areas()
    
    elif bbox is not None and len(bbox_list) != 4:  # Check is the bbox has 4 inputs
        raise HTTPException(status_code=400, detail="Invalid bounding box coordinates. Ensure that the bbox list contains exactly 4 values.")
    
    else:  # Runs when any filteres are entered
        if bbox_list is not None:  # Converts the strings into floats and checks if they are valid numbers
            for i in range(len(bbox_list)):
                try:
                    bbox_list[i] = float(bbox_list[i])
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid bounding box coordinate: {bbox_list[i]}. Ensure that all values are valid numbers.")
        return ParkingAreaHandler().get_parking_areas(name, bbox_list, limit, offset)

# Gets a specific parking area by its ID (ID must be a positive integer)
@app.get("/api/v1/parking_areas/{parking_area_id}")
async def get_parking_area(parking_area_id: int):
    if parking_area_id < 1:
        print("parking_area_id is less than 1")
        raise HTTPException(status_code=400, detail="Invalid parking_area_id. Must be a positive integer.")
    else:
        print("parking_area_id is valid")
        return ParkingAreaHandler().get_parking_area_by_id(parking_area_id)

# Deletes a specific parking area by its ID (ID must be a positive integer)
@app.delete("/api/v1/parking_areas/{parking_area_id}")
async def delete_parking_area(parking_area_id: int):
    if parking_area_id < 1:
        print("parking_area_id is less than 1")
        raise HTTPException(status_code=400, detail="Invalid parking_area_id. Must be a positive integer.")
    else:
        print("parking_area_id is valid")
        return ParkingAreaHandler().delete_parking_area_by_id(parking_area_id)

app.include_router(vehicle_router)
app.include_router(road_segment_router)
app.include_router(location_ping_router)
app.include_router(vehicle_pings_router)
app.include_router(trip_router)
app.include_router(vehicle_trips_router)
app.include_router(assignment_router)
# app.include_router(parking_area_router)


if __name__ == "__main__":
    uvicorn.run(
        "api.v1.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        reload=False,
    )
