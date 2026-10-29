from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from psycopg2.pool import ThreadedConnectionPool

from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
from api.v1.dao.vehicle import ensure_vehicle_constraints
from api.v1.handler.vehicle import router as vehicle_router


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
            "health": "/health",
        },
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(vehicle_router)


if __name__ == "__main__":
    uvicorn.run(
        "api.v1.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        reload=False,
    )
