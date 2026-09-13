"""Read the pilot cost ledger; optionally refresh the Azure budget reading.

This is a reporting command, not a resource controller or hard spending cap.
Run with the repository Python and --refresh after each cloud test session.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATE = ROOT / ".local" / "azure-pilot"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(), parse_float=Decimal)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Read Azure budget; creates no resources")
    args = parser.parse_args()
    plan = read_json(ROOT / "infra/azure-sandbox-pilot/budget-plan.json")
    ledger = read_json(STATE / "ledger.json")
    budget_path = STATE / "verified-budget.json"
    if args.refresh:
        subscription = str(UUID(ledger["subscription_id"]))
        # Fixed pilot scope: this helper cannot query or mutate arbitrary resources.
        url = (
            f"https://management.azure.com/subscriptions/{subscription}"
            "/resourceGroups/rg-sandbox-lab-pilot/providers/Microsoft.Consumption"
            "/budgets/sandbox-lab-testing-200?api-version=2024-08-01"
        )
        result = subprocess.run(
            ["sh", str(ROOT / "scripts/azure_pilot_az.sh"), "rest", "--method", "get",
             "--url", url, "-o", "json"],
            check=True, capture_output=True, text=True, timeout=90,
        )
        budget = json.loads(result.stdout)
        temporary = budget_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(budget, indent=2))
        temporary.replace(budget_path)

    budget = read_json(budget_path) if budget_path.exists() else {}
    reported_spend = budget.get("properties", {}).get("currentSpend")
    receipts = [read_json(path) for path in sorted(STATE.glob("smoke-*.json"))]
    estimated_compute = sum(
        (Decimal(str(r.get("conservative_compute_estimate_usd", 0))) for r in receipts),
        Decimal(0),
    )
    unresolved = [r["run_id"] for r in receipts if not r.get("deleted")]
    prices = plan["retail_prices_before_tax_and_discounts"]
    hourly = {
        name: str(3600 * (
            profile["cpu"] * prices["vcpu_active_per_second"]
            + profile["memory_gib"] * prices["memory_gib_per_second"]
        ))
        for name, profile in plan["profiles"].items()
    }
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_testing_limit_usd": plan["total_testing_limit"],
        "operational_cutoff_usd": plan["operational_cutoff"],
        "safety_reserve_usd": plan["unallocated_safety_reserve"],
        "azure_budget_current_spend": reported_spend,
        "azure_reading_refreshed_now": args.refresh,
        "hourly_active_compute_usd": hourly,
        "recorded_test_compute_estimate_usd": str(estimated_compute),
        "recorded_test_count": len(receipts),
        "unresolved_test_cleanup": unresolved,
        "fixed_cost_approvals": ledger.get("fixed_cost_approvals", []),
        "limitations": [
            "Billing is delayed; this report does not stop compute.",
            "Recorded test estimates exclude storage, requests, network, tax and model calls.",
            "Actual billed and estimated compute figures overlap; do not add them together.",
            "No remaining-budget guarantee until all usage and commitments are reconciled.",
        ],
    }
    if (ROOT / '.local/azure-runtime/budget.sqlite').exists():
        from backend.azure_runtime import AzureRuntime
        runtime = AzureRuntime()
        if args.refresh and reported_spend and reported_spend.get('unit') == 'USD':
            runtime.budget.refresh_billed(float(reported_spend['amount']))
        result['app_runtime_accounting'] = runtime.budget.status()
        result['app_runtime_unresolved_cleanup'] = [
            {'id': row['id'], 'state': row['state']}
            for row in runtime.records() if row['state'] not in ('deleted', 'stopped')
        ]
        result['limitations'].append('The foundation smoke-test subtotal is included in the app runtime initial estimate; do not add it again. App runtime reservations include model calls.')
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
