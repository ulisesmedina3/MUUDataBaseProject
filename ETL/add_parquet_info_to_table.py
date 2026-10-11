import os
from pandas import pd

import psycopg2


def connect_to_database():
    connection = psycopg2.connect(
        host="localhost",
        port=8901,
        dbname="MUU_Database",
        user="MUU",
        password="muu"
    )
    return connection

def add_parquet_info_to_table(connection, parquet_file_path, table_name):
    cursor = connection.cursor()

    collumns = pd.read_parquet(parquet_file_path).columns.tolist()
    values = pd.read_parquet(parquet_file_path).values.tolist()

    cursor.execute(f"INSERT INTO {table_name} ({', '.join(collumns)}) VALUES %s", (values,))
    connection.commit()

def main():
    connection = connect_to_database()
    add_parquet_info_to_table(connection, "phase1_official_dataset/driver.parquet", "driver")


if __name__ == "__main__":
    main()