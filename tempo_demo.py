"""Demonstrate a candidate quote and complete local-fork Router transaction."""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tempo_quote import RpcError, TempoClient, UnsupportedRoute, run_fork_case


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="http://127.0.0.1:8547", help="local Anvil Tempo fork only")
    parser.add_argument("--source", default="cUSD")
    parser.add_argument("--target", default="USDT0")
    parser.add_argument("--amount", default="25", help="human token amount; all supported tokens have six decimals")
    parser.add_argument("--output", type=Path, help="write full JSON including Universal Router calldata")
    args = parser.parse_args()
    try:
        amount = Decimal(args.amount) * 1_000_000
        if amount != amount.to_integral_value() or amount <= 0:
            raise ValueError("amount must be positive with at most six decimal places")
        result = run_fork_case(TempoClient(args.rpc), args.source, args.target, int(amount))
    except (InvalidOperation, ValueError, UnsupportedRoute, RpcError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    view = {k: v for k, v in result.items() if k != "plan"}
    if view["standardQuote"]["status"] == "revert":
        view["standardQuote"] = {"status": "revert", "errorPrefix": view["standardQuote"]["error"][:120],
                                 "fullError": "see --output JSON"}
    if "plan" in result:
        view["plan"] = {k: v for k, v in result["plan"].items() if k != "data"}
        view["calldataBytes"] = (len(result["plan"]["data"]) - 2) // 2
    print(json.dumps(view, indent=2))
    return 0 if result["execution"]["status"] in ("success", "not-attempted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
