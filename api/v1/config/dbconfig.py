import os


POOL_CONFIG = {
    "minconn": 5,
    "maxconn": 10,
}

_DATABASE_VARIABLES = {
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "host": "PGHOST",
    "port": "PGPORT",
}

PG_DB_CONFIG = {
    setting: os.environ.get(variable)
    for setting, variable in _DATABASE_VARIABLES.items()
}
PG_DB_CONFIG["sslmode"] = os.environ.get("PGSSLMODE", "require")

missing_variables = [
    variable
    for variable in _DATABASE_VARIABLES.values()
    if not os.environ.get(variable)
]
if missing_variables:
    raise RuntimeError(
        "Missing database environment variables: " + ", ".join(missing_variables)
    )
