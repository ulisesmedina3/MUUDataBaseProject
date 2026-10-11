
from pathlib import Path
import pandas as pd

# Get the folder where this Python file is located
base_dir = Path(__file__).resolve().parent

# Locate the Parquet file
file_path = (
    base_dir.parent
    / "phase1_official_dataset"
    / "vehicle_assignment.parquet"
)

# Check the file path
print("Looking for:", file_path)
print("File exists:", file_path.exists())

# Read the Parquet file
df = pd.read_parquet(file_path)

# Display information
print(df.head())
print(df.columns.tolist())
print(df.dtypes)
print("Total rows:", len(df))
