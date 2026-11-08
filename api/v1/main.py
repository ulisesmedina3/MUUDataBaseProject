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
from api.v1.handler.parking_area import router as parking_area_router

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
            "parking-area": "/api/v1/parking-areas",
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
app.include_router(parking_area_router)
app.include_router(vehicle_pings_router)
app.include_router(assignment_router)
app.include_router(location_ping_router)
app.include_router(trip_router)
app.include_router(driver_router)
app.include_router(vehicle_trips_router)


@app.exception_handler(RequestValidationError)
async def api_validation_error(
    request: Request, exc: RequestValidationError
):
    if request.method == "POST" and request.url.path == "/api/v1/parking-areas":
        error_types = {error["type"] for error in exc.errors()}
        malformed_json = bool(
            error_types.intersection(
                {"json_invalid", "model_type", "model_attributes_type"}
            )
        )
        messages = "; ".join(
            "Capacity must be greater than 0"
            if error["loc"] == ("body", "capacity")
            and error["type"] == "greater_than_equal"
            else error["msg"]
            for error in exc.errors()
        )
        return JSONResponse(
            status_code=400 if malformed_json else 422,
            content={
                "message": (
                    "Malformed geometry or invalid JSON"
                    if malformed_json
                    else messages
                )
            },
        )

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

    if request.method == "PUT" and request.url.path.startswith(
        "/api/v1/parking-areas/"
    ):
        error_types = {error["type"] for error in exc.errors()}
        if error_types.intersection(
            {"json_invalid", "model_type", "model_attributes_type"}
        ):
            return JSONResponse(
                status_code=400,
                content={"message": "Malformed JSON or invalid update payload"},
            )
        messages = "; ".join(
            "Capacity must be greater than 0"
            if error["loc"] == ("body", "capacity")
            and error["type"] == "greater_than"
            else error["msg"]
            for error in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={"message": messages},
        )

    if request.url.path == "/api/v1/driver" or request.url.path.startswith(
        "/api/v1/driver/"
    ):
        messages = "; ".join(error["msg"] for error in exc.errors())
        return JSONResponse(
            status_code=422,
            content={"message": messages},
        )

    return await request_validation_exception_handler(request, exc)


@app.exception_handler(StarletteHTTPException)
async def api_http_exception(request: Request, exc: StarletteHTTPException):
    if request.method == "PUT" and request.url.path.startswith(
        "/api/v1/parking-areas/"
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
            headers=exc.headers,
        )

    if request.method == "POST" and request.url.path == "/api/v1/parking-areas":
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
            headers=exc.headers,
        )

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
