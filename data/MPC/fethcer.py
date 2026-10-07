import json
from mpc_obscodes import mpc_obscodes
import pandas as pd

sites = pd.DataFrame(json.load(open(mpc_obscodes))).T

sites.to_csv('output_file.csv', index=False)