# hiroute-ref

Install separately from the core with Python 3.11. This distribution contains the independent reference parser, continuous regime optimizer, rational certificate checks, and witness replay. It does not import `hiroute`, `timecut5`, `stopplan4r`, or production planning code.

Run an explicit snapshot with `hiroute-ref --problem snapshot.json --output ref.json`. `H_ref` is a diagnostic finite bound, not an unrestricted infeasibility claim. Output creation is exclusive; an existing result path is never overwritten.
