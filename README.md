<div align="center">

# Car Tracking System

CIIC 4060 / ICOM 5016 – Introduction to Database Systems                         
Department of Electrical and Computer Engineering                              
University of Puerto Rico, Mayagüez Campus                                  
Spring 2026

</div>


## Team Information

**Team Name:** MUU

| Full Name                | Email                                                           |
| ------------------------ | --------------------------------------------------------------- |
| Michael Martinez Curbelo | [michael.martinez21@upr.edu](mailto:michael.martinez21@upr.edu) |
| Ulises L. Medina Hurtado | [ulises.medina3@upr.edu](ulises.medina3@upr.edu)                |
| Uziel J. López Cruz      | [uziel.lopez@upr.edu](mailto:uziel.lopez@upr.edu)               |
      

## Project Overview

Phase I focuses on the design and implementation of the database schema and the development of an ETL pipeline.

The system stores and processes vehicle tracking data using:

* PostgreSQL 17
* PostGIS extension
* Python (ETL implementation)

All geometries are stored in WGS84 (SRID 4326).

The database is hosted in Render as required by the project specifications.

## Virtual environment

Create and activate a virtual environment, then install dependencies:

```bash
# From project root
py -m venv .venv

```
Restart the terminal to activate the ps1 file
```bash
.\.venv\Scripts\Activate.ps1
```
```bash
# Install requirements
py -m pip install -r requirements.txt

$env:PGHOST = "dpg-db4o9b942hec73ecq3t0-a.oregon-postgres.render.com"
$env:PGPORT = "5432"
$env:PGDATABASE = "muu_me05"
$env:PGUSER = "muu_me05_user"
$env:PGPASSWORD = "PwFwz9ljZllk4Bs4s9c7WzbTaU3RDyz2"
$env:PGSSLMODE = "require"
```

## Creating Tables and Loading Data

Run main:

```bash
py ETL/main.py
```

What this script does automatically:
- Runs [sql/createtables.sql](sql/createtables.sql) (includes `CREATE EXTENSION IF NOT EXISTS postgis`)
- Inserts parquet data in dependency order

## Vehicle API

Install the requirements and start the API locally from the project root:

```bash
.\.venv\Scripts\python.exe -m api.v1.main
```

The local server listens on `http://localhost:5000`. Configure `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, and optionally `PGSSLMODE`
before starting it.

For Render, set those database variables in the service's Environment tab,
install from `requirements.txt`, and use this Start Command:

```bash
gunicorn --bind 0.0.0.0:$PORT "api.v1.main:create_app()"
```

After deployment, opening the service URL (`/`) returns the API status.
Use `/health` for a simple health check and `/api/v1/vehicles` for the
vehicle endpoint. Do not append `localhost` to the Render URL.

Create a vehicle with `POST /api/v1/vehicles`:

```json
{
  "vehicle_type_id": 3,
  "vehicle_status_id": 1,
  "plate_number": "ABC-123",
  "make": "Toyota",
  "model": "Hilux",
  "year": 2024
}
```

The endpoint returns `201 Created` with the generated `vehicle_id`, `400 Bad
Request` for malformed or invalid input, `404 Not Found` when a referenced
vehicle type or status does not exist, and `409 Conflict` when the plate number
already exists. `make` and `model` are optional text fields.
