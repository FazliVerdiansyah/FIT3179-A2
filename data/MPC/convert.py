import numpy as np
import pandas as pd

obs = pd.read_csv("obscodes.csv", dtype={"code": str})
print(obs.columns.tolist())   # check the actual names first

obs = obs.rename(columns={
    "Longitude": "lon_east",
    "cos": "rho_cos",
    "sin": "rho_sin",
})

for c in ["lon_east", "rho_cos", "rho_sin"]:
    obs[c] = pd.to_numeric(obs[c], errors="coerce")

obs = obs.dropna(subset=["lon_east", "rho_cos", "rho_sin"])
obs = obs[(obs.rho_cos != 0) | (obs.rho_sin != 0)]

geocentric = np.degrees(np.arctan2(obs.rho_sin, obs.rho_cos))
f = 1 / 298.257223563
obs["lat"] = np.degrees(np.arctan(np.tan(np.radians(geocentric)) / (1 - f) ** 2))
obs["lon"] = np.where(obs.lon_east > 180, obs.lon_east - 360, obs.lon_east)

obs.to_csv("mpc_sites.csv", index=False)