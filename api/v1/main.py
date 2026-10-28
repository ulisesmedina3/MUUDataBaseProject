from __future__ import annotations

import os

from flask import Flask, jsonify
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

    @app.get("/")
    def api_info():
        return jsonify(
            {
                "message": "MUU Vehicle API is running",
                "endpoints": {
                    "vehicles": "/api/v1/vehicles",
                    "health": "/health",
                },
            }
        )

    @app.get("/health")
    def health_check():
        return jsonify({"status": "ok"})

    app.register_blueprint(
        create_vehicle_handler(get_connection, pool.putconn)
    )

    return app


if __name__ == "__main__":
    create_app().run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )
