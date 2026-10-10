import os

import psycopg2


def connect_to_render_database():
	"""Connect to a Render PostgreSQL database using DATABASE_URL."""
	#database_url = os.environ.get("DATABASE_URL")
    database_url = "postgresql://muu_me05_user:PwFwz9ljZllk4Bs4s9c7WzbTaU3RDyz2@dpg-db4o9b942hec73ecq3t0-a/muu_me05"
	if not database_url:
		raise RuntimeError("Set the DATABASE_URL environment variable first.")

	return psycopg2.connect(database_url, sslmode="require")


if __name__ == "__main__":
	connection = connect_to_render_database()
	try:
		print("Connected to the Render database.")
	finally:
		connection.close()
