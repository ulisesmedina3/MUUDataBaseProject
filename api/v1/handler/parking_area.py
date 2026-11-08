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

    def get_parking_areas(self, name, bbox, limit, offset):
        dao = ParkingAreaDAO()

        if name is None:
            name = None

        #bbox syntax: [min_Longitude, min_Latitiude, max_Longitude, max_Latitude]
        if bbox is not None and (bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
            raise HTTPException(status_code=400, detail="Invalid bounding box coordinates. Ensure that min_Longitude < max_Longitude and min_Latitude < max_Latitude.")

        # If any values are None they are set to a default value
        if limit is None:
            limit = 20
        
        if offset is None:
            offset = 0

        result = dao.get_parking_areas(name, bbox, limit, offset)
        if result[1] == 0:
            raise HTTPException(status_code=404, detail="No parking areas found matching the provided criteria.")
        else:
            return result

    def get_parking_area_by_id(self, parking_area_id: int):
        dao = ParkingAreaDAO()
        result = dao.get_parking_area_by_id(parking_area_id)

        if result is None:
            raise HTTPException(status_code=404, detail=f"Parking area with ID {parking_area_id} not found.")
        else:
            return result

    def delete_parking_area_by_id(self, parking_area_id: int):
        dao = ParkingAreaDAO()
        result = dao.delete_parking_area_by_id(parking_area_id) # Returns a boolean. True if the data deleted successfully

        if result:
            return {"message": "Parking area deleted successfully", "parking_area_id": parking_area_id}
        else:
            raise HTTPException(status_code=404, detail=f"Parking area with ID {parking_area_id} not found.")