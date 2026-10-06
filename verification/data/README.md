# Fixture data of the verification chain

Six delimited files the fixtures of `verification/chain.toml` read through a DF data source:
synthetic rows under the TPC-DS table and column names, written by `generate.py` (standard
library, deterministic — run it only when the data has to change, and commit what it writes).

| File | Rows | What |
|---|---|---|
| `income_band.csv` | 20 | the TPC-DS definition: bands of 10,000 |
| `household_demographics.csv` | 7,200 | the TPC-DS definition: every band × buy potential × dependants × vehicles once |
| `reason.csv` | 35 | invented return reasons; the first six read like product reviews |
| `store_returns.csv` | 2,000 | invented, with `NULL` date and reason keys |
| `web_returns.csv` | 1,000 | invented, with `NULL` date and reason keys |
| `store.csv` | 21 | the TPC-DS store dimension's layout: twelve stores kept as validity-dated versions, one closed, two versions of one store starting the same day |

**How the server reads them.** `fixture_route` and `fixture_base` in `[values]` of the manifest:
by default over HTTP from this repository on GitHub. A server that cannot reach GitHub reads them
from a folder on its own disk — copy this folder there and set, in the values file beside your
profiles (`~/.denodo/verify.toml`):

```toml
[<your profile>]
fixture_route = "LOCAL 'LocalConnection'"
fixture_base = "/path/on/the/server/verification-data"
```
