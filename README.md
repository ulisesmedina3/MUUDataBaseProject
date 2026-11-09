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
| Michael Martinez Curbelo | [michael.martinez21@upr.edu](mailto:michael.martinez21@upr.edu) |vehicle, trip, vehicle_assigment
| Ulises L. Medina Hurtado | [ulises.medina3@upr.edu](ulises.medina3@upr.edu)                |road-segment, location-ping
| Uziel J. López Cruz      | [uziel.lopez@upr.edu](mailto:uziel.lopez@upr.edu)               |parking-area, driver
      

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

## API v1

The `api\v1` package provides the version 1 FastAPI interface for accessing the
vehicle-tracking database through HTTP endpoints.
