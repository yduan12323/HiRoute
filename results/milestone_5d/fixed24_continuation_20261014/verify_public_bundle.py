"""Validate public accounting consistency; does not independently rerun raw receipts."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

REPORT_SHA = '66d000910bad4b4fd39368f9483eb380523e54c238e29867a3330d2b7805333a'
AUDIT_SHA = '37e2938cb158e3a94847d6d4b1c11aa9e29151743b86620c467842721f254588'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(root):
    root = Path(root)
    require(digest(root/'public_report.json') == REPORT_SHA, 'Report bytes differ')
    require(digest(root/'public_receipt_audit.json') == AUDIT_SHA, 'Audit bytes differ')
    report = json.loads((root/'public_report.json').read_text())
    audit = json.loads((root/'public_receipt_audit.json').read_text())
    verify_records(report, audit)
    require(digest(root/'generator/build_report.py') == report['provenance']['generator_sha256'], 'Generator source differs')
    require(digest(root/'generator/audit_final_report.py') == audit['audit_source_sha256'], 'Historical audit source differs')
    return {'result': 'PASS', 'scope': 'public hashes and accounting consistency only',
            'denominator': 24, 'time_limit': 23, 'infrastructure_unknown': 1,
            'exact_results': 0, 'raw_receipts_reexecuted': False}

def verify_records(report, audit):
    rows = report['rows']
    require(report['denominator'] == len(rows) == 24, 'Denominator differs')
    require(len({r['row_id'] for r in rows}) == 24, 'Repeated identity')
    require(all(r['denominator_included'] is True for r in rows), 'Excluded identity')
    require(Counter(r['status'] for r in rows) == report['status_counts'] == {'time_limit':23, 'infrastructure_unknown':1}, 'Status counts differ')
    require(report['pending_rows'] == 0 and report['mode'] == 'terminal_accounting', 'Nonterminal report')
    require(report['acceptance'] == 'not_established', 'Unsupported acceptance claim')
    require(rows[1]['status'] == 'infrastructure_unknown' and rows[1]['cleanup_verified'] is None, 'Unknown interruption changed')
    require(all(r['last_durable_phase'] == 'seed_started' and r['exact_outcome'] is None and r['transport_benefit'] == 'not_established' for r in rows), 'Unsupported result claim')
    require(all(p['comparison'] == 'unavailable' and p['flat_over_hier_wall_ratio'] is None for p in report['pairs']), 'Unsupported timing claim')
    require(audit['normalized_report_sha256'] == REPORT_SHA, 'Audit binds another report')
    require(audit['denominator'] == 24 and audit['verified_clean_wall_timeouts'] == 23 and audit['infrastructure_unknown'] == 1 and audit['exact_results'] == audit['comparable_exact_pairs'] == 0, 'Audit summary differs')
    require(len(audit['rows']) == 23 and {r['index'] for r in audit['rows']} == set(range(24))-{1}, 'Audit receipt coverage differs')
    for receipt in audit['rows']:
        row = rows[receipt['index']]
        require(receipt['row_id'] == row['row_id'] and receipt['cleanup_verified'] is row['cleanup_verified'] is True, 'Receipt identity/cleanup differs')
        for key in ('receipt_sha256', 'phase_sha256'):
            require(len(receipt[key]) == 64 and all(c in '0123456789abcdef' for c in receipt[key]), 'Invalid digest')
    charge = sum((Decimal(str(r['conservative_cpu_charge_seconds'])) for i,r in enumerate(rows) if i != 1), Decimal(0))
    require(charge == Decimal(audit['known_row_conservative_charge_decimal_seconds']), 'Charge differs')
    require(charge + Decimal(670+480) == Decimal(audit['conservative_accounted_total_decimal_seconds']), 'Conservative total differs')
    require(report['continuation_accounting']['unique_total_measured_CPU_seconds'] is None, 'Invented measured CPU')
    require(report['historical_48h_accounting']['status'] == 'unreconciled_host_tail', 'Historical accounting changed')

if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parent), indent=2, sort_keys=True))
