import os
import pandas as pd

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values


def connect_to_database():
    connection = psycopg2.connect(
        host="dpg-db4o9b942hec73ecq3t0-a.oregon-postgres.render.com",
        port=5432,
        dbname="muu_me05",
        user="muu_me05_user",
        password="PwFwz9ljZllk4Bs4s9c7WzbTaU3RDyz2"
    )
    return connection

def add_parquet_info_to_table(connection, parquet_file_path, table_name):
    dataframe = pd.read_parquet(parquet_file_path)
    dataframe = dataframe.astype(object).where(pd.notna(dataframe), None)
    columns = dataframe.columns.tolist()
    values = dataframe.itertuples(index=False, name=None)
    statement = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    statement += sql.SQL(" ON CONFLICT DO NOTHING")

    with connection.cursor() as cursor:
        execute_values(cursor, statement.as_string(connection), values)
    connection.commit()

def main():
    connection = connect_to_database()
    load_order = [
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
    ]

    try:
        for table_name in load_order:
            parquet_path = f"phase1_official_dataset/{table_name}.parquet"
            add_parquet_info_to_table(connection, parquet_path, table_name)
            print(f"Loaded {table_name}.")
    finally:
        connection.close()

if __name__ == "__main__":
    main()