import pandas as pd

BASE = "data/interim/lap10/lap10_base.csv"
MISSING = "data/interim/lap10/lap10_base_missing.csv"

base = pd.read_csv(BASE)
missing = pd.read_csv(MISSING)

combined = pd.concat([base, missing], ignore_index=True)

# Stable key for your schema
combined = combined.drop_duplicates(subset=["year", "event_name", "driver_number"], keep="first")

combined.to_csv(BASE, index=False)

print("✅ Updated:", BASE)
print("Rows:", len(combined))
print("Races:", combined[["year", "event_name"]].drop_duplicates().shape[0])
print("Winner rows:", int(combined["is_winner"].sum()))