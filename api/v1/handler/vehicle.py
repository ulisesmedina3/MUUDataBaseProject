from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from api.v1.dao.vehicle import (
    DuplicatePlateError,
    VehicleReferenceNotFoundError,
    create_vehicle,
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def create_vehicle_handler(
    connection_factory: Callable[[], Any],
    connection_releaser: Callable[[Any], None],
):
    blueprint = Blueprint("vehicles", __name__)

    @blueprint.post("/api/v1/vehicles")
    def create_vehicle_route():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400

        required_ids = ("vehicle_type_id", "vehicle_status_id")
        if any(not _is_int(payload.get(field)) for field in required_ids):
            return (
                jsonify(
                    {
                        "error": (
                            "vehicle_type_id and vehicle_status_id are required "
                            "integers"
                        )
                    }
                ),
                400,
            )

        plate_number = payload.get("plate_number")
        if not isinstance(plate_number, str) or not plate_number.strip():
            return jsonify({"error": "plate_number must be a non-empty string"}), 400

        year = payload.get("year")
        if not _is_int(year) or not 1950 <= year <= 2100:
            return jsonify({"error": "year must be between 1950 and 2100"}), 400

        optional_values: dict[str, str | None] = {}
        for field in ("make", "model"):
            value = payload.get(field)
            if value is not None and not isinstance(value, str):
                return jsonify({"error": f"{field} must be a string"}), 400
            optional_values[field] = value.strip() if value is not None else None

        connection = connection_factory()
        try:
            vehicle = create_vehicle(
                connection,
                payload["vehicle_type_id"],
                payload["vehicle_status_id"],
                plate_number.strip(),
                optional_values["make"],
                optional_values["model"],
                year,
            )
        except VehicleReferenceNotFoundError:
            return (
                jsonify(
                    {
                        "error": (
                            "vehicle_type_id or vehicle_status_id does not exist"
                        )
                    }
                ),
                404,
            )
        except DuplicatePlateError:
            return jsonify({"error": "plate_number already exists"}), 409
        finally:
            connection_releaser(connection)

        vehicle["created_at"] = vehicle["created_at"].isoformat()
        return jsonify(vehicle), 201

    return blueprint
