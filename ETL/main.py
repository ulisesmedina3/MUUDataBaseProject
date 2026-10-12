from pathlib import Path

from add_parquet_info_to_table import add_parquet_info_to_table
from createtable import connect_to_database, create_tables


LOAD_ORDER = (
    "vehicle_kind",
    "fuel_type",
    "vehicle_status",
    "parking_area",
    "road_segment",
    "driver",
    "vehicle_type",
    "vehicle",
    "location_ping",
    "trip",
    "vehicle_assignment",
)


def main():
    dataset_directory = Path(__file__).resolve().parent.parent / "phase1_official_dataset"
    connection = connect_to_database()

    try:
        create_tables(connection)
        print("Tables created successfully!")

        for table_name in LOAD_ORDER:
            parquet_path = dataset_directory / f"{table_name}.parquet"
            if not parquet_path.is_file():
                raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

            add_parquet_info_to_table(connection, str(parquet_path), table_name)
            print(f"Loaded {table_name}.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()