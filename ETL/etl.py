import os

import psycopg2

# def connect_to_render_database():
# 	"""Connect to a Render PostgreSQL database using DATABASE_URL."""
# 	#database_url = os.environ.get("DATABASE_URL")
#     database_url = "postgresql://muu_me05_user:PwFwz9ljZllk4Bs4s9c7WzbTaU3RDyz2@dpg-db4o9b942hec73ecq3t0-a/muu_me05"
# 	if not database_url:
# 		raise RuntimeError("Set the DATABASE_URL environment variable first.")

# 	return psycopg2.connect(database_url, sslmode="require")
def connect_to_local_database():
    """Connect to the local PostgreSQL Docker container."""
    #REPLACE WITH YOUR LOCAL DATABASE CREDENTIALS
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5433"),
        user=os.environ.get("PGUSER", "querycommanders"),
        password=os.environ.get("PGPASSWORD", "querycommanders2026"),
        dbname=os.environ.get("PGDATABASE", "Car_Tracking_Test"),
    )

# TODO : Add data from parquet file to the fuel_type table
def create_fuel_type_table(connection):
    """Create and seed the fuel_type lookup table."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fuel_type (
                fuel_type_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
    connection.commit()


if __name__ == "__main__":
    with connect_to_local_database() as connection:
        create_fuel_type_table(connection)
        print("Created and seeded the fuel_type table.")
    
    # connection = connect_to_render_database()
	# try:
	# 	print("Connected to the Render database.")
	# finally:
	# 	connection.close()
    
