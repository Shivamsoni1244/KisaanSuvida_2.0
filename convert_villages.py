import pandas as pd

# Read complete Indian village dataset
df = pd.read_parquet("data/lgd/lgd_villages.parquet")

print("Total villages:", len(df))
print("Columns:", df.columns.tolist())

# Export CSV
df.to_csv(
    "data/lgd/villages.csv",
    index=False,
    encoding="utf-8-sig"
)

print("Village CSV created successfully!")