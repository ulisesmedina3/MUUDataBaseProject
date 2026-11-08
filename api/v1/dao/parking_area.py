from __future__ import annotations

from typing import Any
from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
import psycopg2
from datetime import datetime
from pydantic import BaseModel, Field
from psycopg2.pool import SimpleConnectionPool

# These are the attributes of the ParkingArea table in the database
class ParkingArea(BaseModel):
    parking_area_id: int
    name: str
    capacity: int
    geom: str
    created_at: datetime

class ParkingAreaDAO():
    def __init__(self):
        self.pool = SimpleConnectionPool(POOL_CONFIG["minconn"], POOL_CONFIG["maxconn"], **PG_DB_CONFIG)

    # Gets all of the parking areas in the database
    def get_all_parking_areas(self) -> list[ParkingArea]:
        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                SELECT parking_area_id, name, capacity, ST_AsText(geom), created_at
                FROM parking_area
                """
        cursor.execute(query) # Execute the query and stores the result in the cursor
        result : list[ParkingArea] = [] # Create a list to hold the results
        for row in cursor: # Loops through each row of the table queried by the cursor and creates a ParkingArea object for each row and appends it to the result list
            result.append(ParkingArea(
                parking_area_id=row[0],
                name=row[1],
                capacity=row[2],
                geom=row[3],
                created_at=row[4]
            ))
        
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        return result, len(result)

    def get_parking_areas(self, name: str, bbox: list[int], limit: int, offset: int) -> list[ParkingArea]:
        print(f"Input: name={name}, bbox={bbox}, limit={limit}, offset={offset}")

        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                SELECT parking_area_id, name, capacity, ST_AsText(geom), created_at
                """

        # If name and bbox are provided, the query will adjusted accordingly
        if name and bbox:
            query += """
                    FROM parking_area
                    WHERE name = %s AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """
            cursor.execute(query, (f"{name}", bbox[0], bbox[1], bbox[2], bbox[3], limit, offset))
        elif name and not bbox:
            query += """
                    FROM parking_area
                    WHERE name = %s
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """
            cursor.execute(query, (f"{name}", limit, offset))
        elif not name and bbox:
            query += """
                    FROM parking_area
                    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """
            cursor.execute(query, (bbox[0], bbox[1], bbox[2], bbox[3], limit, offset))
        else:
            query += """
                    FROM parking_area
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """
            cursor.execute(query, (limit, offset))

        result : list[ParkingArea] = [] # Create a list to hold the results
        for row in cursor: # Loops through each row of the table queried by the cursor and creates a ParkingArea object for each row and appends it to the result list
            result.append(ParkingArea(
                parking_area_id=row[0],
                name=row[1],
                capacity=row[2],
                geom=row[3],
                created_at=row[4]
            ))
        
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        return result, len(result)
    
    def get_parking_area_by_id(self, parking_area_id: int) -> ParkingArea | None:
        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                SELECT parking_area_id, name, capacity, ST_AsText(geom), created_at
                FROM parking_area
                WHERE parking_area_id = %s
                """
        cursor.execute(query, (parking_area_id,)) # Execute the query and stores the result in the cursor
        row = cursor.fetchone() # Fetches the first row of the result set

        if row is None:
            cursor.close() # Close the cursor
            self.pool.putconn(conn) # Return the connection to the pool
            print("Does not exist")
            return None
        
        parking_area = ParkingArea(
            parking_area_id=row[0],
            name=row[1],
            capacity=row[2],
            geom=row[3],
            created_at=row[4]
        )
        
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        print("Does exist")
        return parking_area
    
    def delete_parking_area_by_id(self, parking_area_id: int) -> bool:
        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                DELETE FROM parking_area
                WHERE parking_area_id = %s
                """
        cursor.execute(query, (parking_area_id,)) # Execute the query and stores the result in the cursor
        rows_affected = cursor.rowcount # Get the number of rows affected by the delete operation
        
        conn.commit() # Commit the transaction to make the deletion permanent
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        print("Deleted")
        return rows_affected == 1