"""Build reproducible static Sites and geographic support, without new OSM data."""
import argparse
import json
import time

import pandas as pd

from _stopplan4r_common import ROOT, memory_guard, peak_rss_mib, read_config, sha256, write_json
from stopplan4r.sites import build_sites, validate_static_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/stopplan_4r.yaml')
    args = parser.parse_args()
    cfg = read_config(args.config)
    out = ROOT / cfg['results_dir']; out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    guard = memory_guard(cfg['memory'], projected_additional_gib=1)
    inventory, attachment = pd.read_parquet(ROOT / cfg['inventory']), pd.read_parquet(ROOT / cfg['attachments'])
    table, support, stats = build_sites(inventory, attachment, cfg['support']['radii_m'], cfg['support']['primary_radius_m'])
    table.to_parquet(out / 'stop_sites.parquet', index=False, compression='zstd')
    support.to_parquet(out / 'local_support.parquet', index=False, compression='zstd')
    validate_static_table(pd.read_parquet(out / 'stop_sites.parquet'))
    first_build_s = time.perf_counter() - start
    # Independent reconstruction with reordered inputs; typed-ID order and bytes
    # must be unchanged. No duplicate-looking facility merging is performed.
    rebuild_start = time.perf_counter()
    again, again_support, _ = build_sites(inventory.iloc[::-1], attachment.iloc[::-1],
                                        cfg['support']['radii_m'], cfg['support']['primary_radius_m'])
    again.to_parquet(out / 'stop_sites_rebuild.parquet', index=False, compression='zstd')
    again_support.to_parquet(out / 'local_support_rebuild.parquet', index=False, compression='zstd')
    byte_identical = all(sha256(out / (name + '.parquet')) == sha256(out / (name + '_rebuild.parquet')) for name in ['stop_sites', 'local_support'])
    if not byte_identical:
        raise ValueError('Reordered-input static reconstruction differs')
    charger_ids = set(table.loc[table.transport_capabilities.map(lambda c: 'charge' in c), 'site_id'])
    coverage = []
    for radius, group in support.groupby('radius_m'):
        charge = group[group.site_id.isin(charger_ids)]
        coverage.append({'radius_m': float(radius), 'site_count': len(group),
            'meal_supported_count': int(group.meal_count.ge(cfg['support']['meal_threshold']).sum()),
            'meal_support_fraction': float(group.meal_count.ge(cfg['support']['meal_threshold']).mean()),
            'toilet_support_fraction': float(group.toilet_count.ge(1).mean()),
            'lodging_support_fraction': float(group.lodging_count.ge(1).mean()),
            'charger_count': len(charge), 'charger_meal_support_fraction': float(charge.meal_count.ge(cfg['support']['meal_threshold']).mean())})
    pd.DataFrame(coverage).to_csv(out / 'support_coverage.csv', index=False)
    counts = {cap: int(table.transport_capabilities.map(lambda c: cap in c).sum()) for cap in ['charge', 'parking', 'rest', 'services']}
    static_contract = {'inventory_sha256': sha256(ROOT / cfg['inventory']),
        'attachments_sha256': sha256(ROOT / cfg['attachments']),
        'radii_m': cfg['support']['radii_m'], 'primary_radius_m': cfg['support']['primary_radius_m'],
        'method': cfg['support']['method']}
    record = {'command': ' '.join(__import__('sys').argv), 'configuration': cfg, 'static_contract': static_contract,
        'inputs': {p: sha256(ROOT / p) for p in [cfg['inventory'], cfg['attachments'], args.config]},
        'raw_opportunity_count': len(inventory), 'site_count': len(table),
        'attached_site_count': int(table.attachment_status.eq('attached').sum()),
        'counts_by_transport_capability_nonexclusive': counts,
        'capability_rule': 'exact intersection with existing M4A charge/parking/rest/services; one Site per raw OSM identity',
        'attachment_status_counts': {str(k): int(v) for k, v in table.attachment_status.value_counts().items()},
        'support_coverage': coverage, 'support_runtime': stats, 'first_build_seconds': first_build_s,
        'rebuild_seconds': time.perf_counter() - rebuild_start, 'peak_rss_mib': peak_rss_mib(),
        'memory_preflight': guard, 'byte_identical_reordered_rebuild': byte_identical,
        'static_columns': sorted(table.columns),
        'outputs': {name: sha256(out / name) for name in ['stop_sites.parquet', 'local_support.parquet', 'support_coverage.csv']}}
    write_json(out / 'site_build.json', record)
    print(json.dumps({k: record[k] for k in ['raw_opportunity_count', 'site_count', 'attached_site_count', 'counts_by_transport_capability_nonexclusive', 'first_build_seconds', 'peak_rss_mib', 'byte_identical_reordered_rebuild']}, indent=2))


if __name__ == '__main__':
    main()
