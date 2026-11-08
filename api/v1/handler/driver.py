from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.driver import (
    DriverDAO,
    DriverDeleteConflictError,
    DriverLicenseConflictError,
    DriverNotFoundError,
)

router = APIRouter(prefix="/api/v1/driver", tags=["driver"])


class DriverCreate(BaseModel):
    first_name: str = Field(min_length=1, strip_whitespace=True)
    last_name: str = Field(min_length=1, strip_whitespace=True)
    license_number: str = Field(min_length=1, strip_whitespace=True)
    hired_at: datetime | None = None


class DriverUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, strip_whitespace=True)
    last_name: str | None = Field(default=None, min_length=1, strip_whitespace=True)
    license_number: str | None = Field(default=None, min_length=1, strip_whitespace=True)
    hired_at: datetime | None = None


def _connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


@router.post("", status_code=201)
async def create_driver(payload: DriverCreate, request: Request):
    pool, connection = _connection(request)
    try:
        return DriverDAO.create_driver(
            connection,
            first_name=payload.first_name,
            last_name=payload.last_name,
            license_number=payload.license_number,
            hired_at=payload.hired_at,
        )
    except DriverLicenseConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="license_number already exists",
        ) from exc
    finally:
        pool.putconn(connection)

# Gets a query of the driver table
@router.get("", status_code=200)
async def get_drivers(
    request: Request,
    first_name: str | None = None,
    last_name: str | None = None,
    license_number: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    if limit < 0:
        raise HTTPException(status_code=400, detail="limit must be a non-negative integer")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be a non-negative integer")

    normalized_first_name = first_name.strip() if first_name is not None and first_name.strip() else None
    normalized_last_name = last_name.strip() if last_name is not None and last_name.strip() else None
    normalized_license_number = license_number.strip() if license_number is not None and license_number.strip() else None

    pool, connection = _connection(request)
    try:
        items, count = DriverDAO.get_drivers(
            connection,
            first_name=normalized_first_name,
            last_name=normalized_last_name,
            license_number=normalized_license_number,
            limit=limit,
            offset=offset,
        )
    finally:
        pool.putconn(connection)

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "count": count,
    }


# Gets a driver by its ID
@router.get("/{driver_id}", status_code=200)
async def get_driver(request: Request, driver_id: int):
    if driver_id <= 0:
        raise HTTPException(status_code=400, detail="driver_id must be a positive integer")

    pool, connection = _connection(request)
    try:
        try:
            return DriverDAO.get_driver_by_id(connection, driver_id)
        except DriverNotFoundError as exc:
            raise HTTPException(status_code=404, detail="driver_id does not exist") from exc
    finally:
        pool.putconn(connection)

# Update a driver by its ID
@router.put("/{driver_id}", status_code=200)
async def update_driver(
    request: Request,
    driver_id: int,
    payload: DriverUpdate,
):
    if driver_id <= 0:
        raise HTTPException(status_code=400, detail="driver_id must be a positive integer")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    if any(
        data[field] is None
        for field in ("first_name", "last_name", "license_number")
        if field in data
    ):
        raise HTTPException(
            status_code=400,
            detail="first_name, last_name, and license_number cannot be null",
        )

    pool, connection = _connection(request)
    try:
        try:
            return DriverDAO.update_driver(connection, driver_id, data)
        except DriverNotFoundError as exc:
            raise HTTPException(status_code=404, detail="driver_id does not exist") from exc
        except DriverLicenseConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail="license_number already exists",
            ) from exc
    finally:
        pool.putconn(connection)

# Deletes a driver via their ID
@router.delete("/{driver_id}", status_code=200)
async def delete_driver(request: Request, driver_id: int):
    if driver_id <= 0:
        raise HTTPException(status_code=400, detail="driver_id must be a positive integer")

    pool, connection = _connection(request)
    try:
        try:
            return DriverDAO.delete_driver(connection, driver_id)
        except DriverNotFoundError as exc:
            raise HTTPException(status_code=404, detail="driver_id does not exist") from exc
        except DriverDeleteConflictError as exc:
            raise HTTPException(status_code=409, detail="Driver is referenced and cannot be deleted",
            ) from exc
    finally:
        pool.putconn(connection)