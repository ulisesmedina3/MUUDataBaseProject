from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg2.pool import ThreadedConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
from api.v1.dao.vehicle import ensure_vehicle_constraints
from api.v1.handler.vehicle import router as vehicle_router
from api.v1.handler.road_segment import router as road_segment_router
from api.v1.handler.location_ping import router as location_ping_router, vehicle_pings_router
from api.v1.handler.trip import router as trip_router, vehicle_trips_router
from api.v1.handler.vehicle_assignment import router as assignment_router
from api.v1.handler.driver import router as driver_router

from api.v1.dao.parking_area import (
    InvalidParkingAreaGeometryError,
    ParkingAreaDAO,
    ParkingAreaCreate,
    ParkingAreaNotFoundError,
    ParkingAreaUpdate,
)
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
            "road-segments": "/api/v1/road-segments",
            "parking-areas": "/api/v1/parking_areas",
            "location-pings": "/api/v1/location-pings",
            "trips": "/api/v1/trips",
            "drivers": "/api/v1/drivers",
            "vehicle-assignments": "/api/v1/vehicle-assignments",
            "health": "/health",
        },
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(vehicle_router)
app.include_router(road_segment_router)
# app.include_router(parking_area_router)
app.include_router(vehicle_pings_router)
app.include_router(assignment_router)
app.include_router(location_ping_router)
app.include_router(trip_router)
app.include_router(driver_router)
app.include_router(vehicle_trips_router)

# ==========================
# 5.3 Parking Area
# ==========================

@app.post("/api/v1/parking-areas", status_code=201)
async def create_parking_area(payload: ParkingAreaCreate, request: Request):
    try:
        return ParkingAreaHandler().create_parking_area(request, payload)
    except InvalidParkingAreaGeometryError as exc:
        raise HTTPException(
            status_code=400,
            detail="Malformed geometry or invalid JSON",
        ) from exc


# Get a query of all parking areas or a filtered query
@app.get("/api/v1/parking-areas")
async def get_parking_areas(name: str | None = None, bbox: str | None = None, limit: int = 20, offset: int = 0):
    if limit < 0:
        raise HTTPException(status_code=400, detail="Limit cannot be negative.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset cannot be negative.")

    bbox_values: list[float] | None = None
    if bbox is not None:
        try:
            bbox_values = [float(value) for value in bbox.split(",")]
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid bounding box coordinates.",
            ) from exc
        if len(bbox_values) != 4:
            raise HTTPException(
                status_code=400,
                detail="Bounding box must contain exactly four coordinates.",
            )

    handler = ParkingAreaHandler()
    if name is None and bbox_values is None:
        return handler.get_all_parking_areas(limit, offset)
    return handler.get_parking_areas(name, bbox_values, limit, offset)


# Gets a specific parking area by its ID (ID must be a positive integer)
@app.get("/api/v1/parking-areas/{parking_area_id}")
async def get_parking_area(parking_area_id: int):
    if parking_area_id < 1:
        raise HTTPException(status_code=400, detail="Invalid parking_area_id. Must be a positive integer.")
    else:
        print("parking_area_id is valid")
        return ParkingAreaHandler().get_parking_area_by_id(parking_area_id)


# Deletes a specific parking area by its ID (ID must be a positive integer)
@app.delete("/api/v1/parking-areas/{parking_area_id}")
async def delete_parking_area(parking_area_id: int):
    if parking_area_id < 1:
        print("parking_area_id is less than 1")
        raise HTTPException(status_code=400, detail="Invalid parking_area_id. Must be a positive integer.")
    else:
        print("parking_area_id is valid")
        return ParkingAreaHandler().delete_parking_area_by_id(parking_area_id)


# Edits a parking area by its ID
@app.put("/api/v1/parking-areas/{parking_area_id}")
async def update_parking_area(
    parking_area_id: int, payload: ParkingAreaUpdate, request: Request
):
    if parking_area_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="parking_area_id must be a positive integer",
        )

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update.",
        )

    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    connection = pool.getconn()
    try:
        return ParkingAreaDAO.update_parking_area(
            connection, parking_area_id, updates
        )
    except ParkingAreaNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Parking area with ID {parking_area_id} not found.",
        ) from exc
    except InvalidParkingAreaGeometryError as exc:
        raise HTTPException(
            status_code=400,
            detail="geom must be a valid GeoJSON Polygon.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        pool.putconn(connection)


@app.exception_handler(RequestValidationError)
async def api_validation_error(
    request: Request, exc: RequestValidationError
):
    if request.method == "POST" and request.url.path == "/api/v1/driver":
        error_types = {error["type"] for error in exc.errors()}
        if error_types.intersection(
            {"json_invalid", "model_type", "model_attributes_type"}
        ):
            return JSONResponse(
                status_code=400,
                content={"message": "Malformed JSON or invalid payload shape"},
            )
        return JSONResponse(
            status_code=422,
            content={"message": "A required field is null or invalid"},
        )

    if request.method == "PUT" and request.url.path.startswith(
        "/api/v1/driver/"
    ):
        error_types = {error["type"] for error in exc.errors()}
        if error_types.intersection(
            {"json_invalid", "model_type", "model_attributes_type"}
        ):
            return JSONResponse(
                status_code=400,
                content={"message": "Malformed JSON or empty update payload"},
            )

    if request.url.path == "/api/v1/driver" or request.url.path.startswith(
        "/api/v1/driver/"
    ):
        messages = "; ".join(error["msg"] for error in exc.errors())
        return JSONResponse(
            status_code=422,
            content={"message": messages},
        )

    is_parking_area_post = (
        request.method == "POST"
        and request.url.path == "/api/v1/parking_areas"
    )
    is_parking_area_put = (
        request.method == "PUT"
        and request.url.path.startswith("/api/v1/parking_areas/")
    )
    if is_parking_area_post or is_parking_area_put:
        messages = "; ".join(
            "Capacity must be greater than 0"
            if error["loc"] == ("body", "capacity")
            and error["type"] == "greater_than"
            else error["msg"]
            for error in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={"detail": messages},
        )

    return await request_validation_exception_handler(request, exc)


@app.exception_handler(StarletteHTTPException)
async def api_http_exception(request: Request, exc: StarletteHTTPException):
    if request.url.path == "/api/v1/driver" or request.url.path.startswith(
        "/api/v1/driver/"
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
            headers=exc.headers,
        )

    return await http_exception_handler(request, exc)

if __name__ == "__main__":
    uvicorn.run(
        "api.v1.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        reload=False,
    )
