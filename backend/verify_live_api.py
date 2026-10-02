import urllib.request
import json
import os
from decimal import Decimal

# ---------------------------------------------------------------------------
# Configuration — set via environment variables before running:
#   $env:VERIFY_TOKEN     = "<your JWT access token>"
#   $env:VERIFY_CLIENT_ID = "<client UUID for Ankit public Ltd or any client>"
# ---------------------------------------------------------------------------
token = os.environ.get('VERIFY_TOKEN', '')
if not token:
    raise SystemExit(
        'ERROR: Set the VERIFY_TOKEN environment variable to a valid JWT access token.\n'
        '  PowerShell: $env:VERIFY_TOKEN = "<token>"\n'
        '  Bash:       export VERIFY_TOKEN="<token>"'
    )
headers = {'Authorization': f'Bearer {token}'}
cid = os.environ.get('VERIFY_CLIENT_ID', '70796fab-5319-4dfa-a760-36101d3db20c')

results = {}
for ep in ['gstr1', 'gstr2b', 'gstr3b', 'discrepancies', 'table12-hsn']:
    url = f'http://localhost:8000/api/v1/gst/reconciliation/{ep}?client_id={cid}&period=2026-Q2'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            results[ep] = data['data']
            print(f"=== {ep} === OK (HTTP {resp.status})")
    except Exception as e:
        print(f"=== {ep} === ERROR: {e}")

g1 = results.get('gstr1', {})
g3 = results.get('gstr3b', {})
disc = results.get('discrepancies', {})
hsn = results.get('table12-hsn', {})

print("\n--- GSTR-1 Summary ---")
print("Total Outward Taxable:", g1.get("total_outward_taxable"))
print("Total Outward Tax:", g1.get("total_outward_tax"))
print("B2B Summary:", g1.get("b2b_summary"))
print("B2C Large Summary:", g1.get("b2c_large_summary"))
print("Credit Notes Summary:", g1.get("credit_notes_summary"))
print("Debit Notes Summary:", g1.get("debit_notes_summary"))

print("\n--- GSTR-3B Summary ---")
print("Table 3.1 Outward:", g3.get("table_3_1_outward"))
print("Table 4 Net ITC:", g3.get("table_4_net_itc"))
print("Tax Payable in Cash:", g3.get("tax_payable_in_cash"))

print("\n--- Discrepancies Summary ---")
print("Total Discrepancies:", disc.get("total_discrepancies"))
print("High Risk Count:", disc.get("high_count"))
print("Medium Risk Count:", disc.get("medium_count"))
for item in disc.get("discrepancies", []):
    print(f"  [{item.get('severity')}] {item.get('discrepancy_type')} - {item.get('description')} (Variance: {item.get('variance')})")

print("\n--- Table 12 HSN Summary ---")
print("Total Records:", hsn.get("total_records"))
print("Total Taxable:", hsn.get("total_taxable_value"))
print("Total Tax:", hsn.get("total_tax_amount"))
for item in hsn.get("hsn_items", []):
    print(f"  HSN {item.get('hsn_sac')}: {item.get('description')} | Rate: {item.get('gst_rate')}% | Taxable: {item.get('taxable_amount')} | Tax: {item.get('total_tax')} | Qty: {item.get('total_quantity')}")

# Save evidence JSON
import os
os.makedirs("../docs/evidence", exist_ok=True)
with open("../docs/evidence/live_reconciliation_c1070.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nSaved live evidence to docs/evidence/live_reconciliation_c1070.json")
