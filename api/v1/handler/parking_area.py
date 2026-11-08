from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from psycopg2.pool import ThreadedConnectionPool
from api.v1.dao.parking_area import ParkingAreaDAO

# from api.v1.dao.parking_area import (
#     # DuplicateParkingAreaError,
#     # ParkingAreaReferenceNotFoundError,
#     # create_parking_area,
#     get_parking_areas,)

class ParkingAreaHandler:
    def get_all_parking_areas(self):
        dao = ParkingAreaDAO()
        return dao.get_all_parking_areas()

    def get_parking_area_by_id(self, parking_area_id: int):
        dao = ParkingAreaDAO()
        result = dao.get_parking_area_by_id(parking_area_id)

        if result is None:
            raise HTTPException(status_code=404, detail=f"Parking area with ID {parking_area_id} not found.")
        else:
            return result