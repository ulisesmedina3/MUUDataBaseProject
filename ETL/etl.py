
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


def connect_to_local_database():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="car_tracking",
        user="postgres",
        password="postgres"
    )


def load_vehicle_assignments(connection):
    # Locate the Parquet file
    base_dir = Path(__file__).resolve().parent

    file_path = (
        base_dir.parent
        / "phase1_official_dataset"
        / "vehicle_assignment.parquet"
    )

    # Read Parquet file
    df = pd.read_parquet(file_path)

    # Convert missing dates to None for PostgreSQL
    df = df.astype(object).where(pd.notna(df), None)

    # Convert rows into tuples
    rows = list(df.itertuples(index=False, name=None))

    # SQL query
    query = """
        INSERT INTO vehicle_assignment (
            assignment_id,
            vehicle_id,
            driver_id,
            assigned_from,
            assigned_to
        )
        VALUES %s;
    """

    # Insert all records
    with connection.cursor() as cursor:
        execute_values(cursor, query, rows, page_size=1000)

    connection.commit()

    print(f"Successfully imported {len(rows)} assignments!")


def main():
    connection = connect_to_local_database()

    try:
        load_vehicle_assignments(connection)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
