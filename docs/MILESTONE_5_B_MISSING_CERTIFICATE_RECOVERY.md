# B64 missing raw-certificate recovery

On 2026-10-10, the exact 12 historical B64 cases whose original-source raw REF certificates were not retained were independently solved on isolated source `6a91a6b18a858a10b5206cad17402db72d5972a8`. The original 64-case input SHA-256 is `61a1d3f86da1c750ef127f7827f4ef68d2b5aa21babc314691ce095ed498f037`; the historical result SHA-256 is `a45979a2a49909d61b25df46d35237120f85c46c8c266cf13b78c7ed627bb025`. Each case was extracted singly with its byte hash in the [receipt](MILESTONE_5_B_MISSING_CERTIFICATE_RECOVERY.json). No other B case was rerun.

B12 was completed first. The other 11 ran under at most four independent guards. Each guard had a 900-second absolute wall limit, 4 GiB child AS and sampled group RSS caps, and a 512 MiB charged output cap. The aggregate watchdog capped sampled RSS at 16 GiB and required 20 GiB host memory available. The generalized guard passed a trivial smoke test. Each attempt preserves stdout, stderr, samples, actual exits, partial files if any, and a terminal result. The 11-case batch finished in 245.01 seconds with 11 successes and no failures; aggregate sampled RSS peaked at 908,144,640 bytes and host available memory never fell below 54,744,981,504 bytes. The longest individual case took 197.17 seconds.

| Case | REF result key `(J,Q,H,actions)` | Certified regimes | Four-mode parity |
| --- | --- | ---: | ---: |
| B01 | (1800, 0, 0, []) | 35983/35983 | 4/4 |
| B02 | (3564, 24, 1, [['u', 'C']]) | 35983/35983 | 4/4 |
| B03 | (1800, 0, 0, []) | 7381/7381 | 4/4 |
| B04 | (3564, 24, 1, [['u', 'C']]) | 7381/7381 | 4/4 |
| B05 | infeasible within H_ref | 0/0 | 4/4 |
| B06 | infeasible within H_ref | 0/0 | 4/4 |
| B09 | (1800, 0, 0, []) | 35983/35983 | 4/4 |
| B10 | (2916, 6, 1, [['u', 'C']]) | 35983/35983 | 4/4 |
| B11 | (1800, 0, 0, []) | 7381/7381 | 4/4 |
| B12 | (2916, 6, 1, [['u', 'C']]) | 7381/7381 | 4/4 |
| B13 | infeasible within H_ref | 0/0 | 4/4 |
| B14 | infeasible within H_ref | 0/0 | 4/4 |

All **173,456** finite regimes across the 12 cases have raw REF certificates; all eight attained witnesses replayed. All **48/48** FLAT/HIER × dominance off/on comparisons matched the fresh REF keys, and all 12 status, full-key and regime counts matched the pinned historical B64 rows. Four infeasible cases have zero admissible finite regimes; their REF and comparator status still agreed. The successful evidence archive is `/Users/dy/Documents/Codex/2026-10-07/task/b-missing-12.001.success.tar.gz`, SHA-256 `6f293fb6a7167ced9ca1500e6627abf019d1cf9c451f886c0bfb5b352fbe6e51`. The server originals and production verifier at `3ad6e385903b631579df059b48d9ea6037728da7` remain unchanged.

This closes only the missing raw-certificate gap for these 12 bounded B64 cases on the stated source. It does not establish current-source acceptance for all B64 cases, literal inherited-family G8, C32, or whole M5-V.
