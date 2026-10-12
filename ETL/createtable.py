import os

import psycopg2

def connect_to_database():
    connection = psycopg2.connect(
        host="dpg-db4o9b942hec73ecq3t0-a.oregon-postgres.render.com",
        port=5432,
        dbname="muu_me05",
        user="muu_me05_user",
        password="PwFwz9ljZllk4Bs4s9c7WzbTaU3RDyz2"
    )
    return connection


def create_tables(connection):
    cursor = connection.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        # 1. Vehicle kind
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_kind (
            vehicle_kind_id BIGINT PRIMARY KEY,
            name TEXT
        );
    """)

    # 2. Fuel type
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fuel_type (
            fuel_type_id BIGINT PRIMARY KEY,
            name TEXT
        );
    """)

    # 3. Vehicle status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_status (
            vehicle_status_id BIGINT PRIMARY KEY,
            name TEXT
        );
    """)

    # 4. Parking area
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parking_area (
            parking_area_id BIGINT PRIMARY KEY,
            name TEXT,
            capacity BIGINT,
            geom GEOMETRY(Polygon, 4326),
            created_at TIMESTAMP
        );
    """)

    # 5. Road segment
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS road_segment (
            road_id BIGINT PRIMARY KEY,
            name TEXT,
            speed_limit_kph BIGINT,
            geom GEOMETRY(LineString, 4326),
            created_at TIMESTAMP,
            is_oneway BOOLEAN,
            direction TEXT
        );
    """)

    # 6. Driver
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver (
            driver_id BIGINT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            license_number TEXT,
            hired_at TIMESTAMP
        );
    """)

    # 7. Vehicle type
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_type (
            vehicle_type_id BIGINT PRIMARY KEY,
            vehicle_kind_id BIGINT
                REFERENCES vehicle_kind(vehicle_kind_id),
            fuel_type_id BIGINT
                REFERENCES fuel_type(fuel_type_id),
            emissions_rating DOUBLE PRECISION,
            created_at TIMESTAMP
        );
    """)

    # 8. Vehicle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle (
            vehicle_id BIGINT PRIMARY KEY,
            vehicle_type_id BIGINT
                REFERENCES vehicle_type(vehicle_type_id),
            vehicle_status_id BIGINT
                REFERENCES vehicle_status(vehicle_status_id),
            plate_number TEXT,
            make TEXT,
            model TEXT,
            year BIGINT,
            created_at TIMESTAMP
        );
    """)

    # 9. Location ping
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS location_ping (
            ping_id BIGINT PRIMARY KEY,
            vehicle_id BIGINT
                REFERENCES vehicle(vehicle_id),
            ts TIMESTAMP,
            geom GEOMETRY(Point, 4326),
            speed_kph DOUBLE PRECISION,
            heading_deg DOUBLE PRECISION
        );
    """)

    # 10. Trip
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trip (
            trip_id BIGINT PRIMARY KEY,
            vehicle_id BIGINT
                REFERENCES vehicle(vehicle_id),
            start_ts TIMESTAMP,
            end_ts TIMESTAMP,
            start_geom GEOMETRY(Point, 4326),
            end_geom GEOMETRY(Point, 4326),
            distance_km DOUBLE PRECISION
        );
    """)

    # 11. Vehicle assignment
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_assignment (
            assignment_id BIGINT PRIMARY KEY,
            vehicle_id BIGINT
                REFERENCES vehicle(vehicle_id),
            driver_id BIGINT
                REFERENCES driver(driver_id),
            assigned_from TIMESTAMP,
            assigned_to TIMESTAMP
        );
    """) 

    connection.commit()
    cursor.close()


# def main():
#     connection = connect_to_database()

#     try:
#         create_tables(connection)
#         print("Tables created successfully!")
#     finally:
#         connection.close()


# if __name__ == "__main__":
#     main()
