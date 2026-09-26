"""Run the verified Tempo quote-dispatch path against a local Anvil fork."""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from quote_dispatch import RouteRequest, dispatch_quotes, validate_tempo_on_fork
from tempo_quote import (HISTORICAL_CONTEXT, RpcError, TempoClient,
                         UnsupportedRoute, resolve_route, standard_quote)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", required=True, help="local Anvil Tempo fork at block 41183156")
    parser.add_argument("--target", choices=["USDT0", "USDC.e", "PathUSD"], default="USDT0")
    parser.add_argument("--amount", default="25", help="cUSD amount, at most six decimals")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = Decimal(args.amount) * 1_000_000
        if raw <= 0 or raw != raw.to_integral_value():
            raise ValueError("amount must be positive with at most six decimals")
        route = resolve_route("cUSD", args.target)
        request = RouteRequest("verified-tempo", route, int(raw))
        client = TempoClient(args.rpc)
        before = standard_quote(client, route, int(raw), HISTORICAL_CONTEXT)
        if before.get("status") == "revert":
            before = {"status": "revert", "errorPrefix": before["error"][:160]}
        result = dispatch_quotes(
            client, [request], HISTORICAL_CONTEXT,
            validator=lambda req, quote, context: validate_tempo_on_fork(
                client, req, quote, context),
        )
    except (InvalidOperation, ValueError, UnsupportedRoute, RpcError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = {"chainId": HISTORICAL_CONTEXT.chain_id,
              "blockNumber": HISTORICAL_CONTEXT.number,
              "blockHash": HISTORICAL_CONTEXT.hash,
              "route": route.label, "amountIn": int(raw),
              "existingStandardQuote": before,
              "dispatch": result, "rpcCalls": client.count}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if result["comparisonInput"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
