from __future__ import annotations

from flask import Flask
from psycopg2.pool import ThreadedConnectionPool

from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
from api.v1.dao.vehicle import ensure_vehicle_constraints
from api.v1.handler.vehicle import create_vehicle_handler


def create_app() -> Flask:
    pool = ThreadedConnectionPool(
        POOL_CONFIG["minconn"],
        POOL_CONFIG["maxconn"],
        **PG_DB_CONFIG,
    )
    connection = pool.getconn()
    try:
        ensure_vehicle_constraints(connection)
    finally:
        pool.putconn(connection)

    def get_connection():
        return pool.getconn()

    app = Flask(__name__)
    app.register_blueprint(
        create_vehicle_handler(get_connection, pool.putconn)
    )

    return app


if __name__ == "__main__":
    create_app().run()
