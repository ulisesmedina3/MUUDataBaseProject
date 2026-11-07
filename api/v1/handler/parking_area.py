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