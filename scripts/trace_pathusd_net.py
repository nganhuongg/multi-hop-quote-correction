"""Reproduce the PathUSD gross/net difference on a fresh local Tempo fork."""

import argparse
import json
from pathlib import Path

from tempo_quote import HISTORICAL_CONTEXT, PAYER, TOKENS, TempoClient, run_fork_case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", required=True, help="fresh local Anvil fork at block 41183156")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    client = TempoClient(args.rpc)
    other = "0x1111111111111111111111111111111111111111"
    cases = []
    for recipient in (PAYER, other):
        result = run_fork_case(client, "cUSD", "PathUSD", 1_000_000, recipient=recipient)
        execution = result["execution"]
        if execution["status"] != "success":
            raise RuntimeError(f"local fork execution failed: {execution}")
        fee = sum(transfer["amount"] for transfer in execution["feeTokenTransfers"])
        expected_fee = (execution["gasUsed"] * execution["effectiveGasPrice"] + 10**12 - 1) // 10**12
        assert execution["feeToken"].lower() == TOKENS["PathUSD"].lower()
        assert execution["feePayer"].lower() == PAYER.lower()
        assert fee == expected_fee
        assert result["candidate"]["amountOut"] == execution["grossOutputTransfer"] == 999_800
        if recipient == PAYER:
            assert execution["recipientDelta"] + fee == execution["grossOutputTransfer"]
        else:
            assert execution["recipientDelta"] == execution["grossOutputTransfer"]
            assert execution["payerOutputBalanceAfter"] - execution["payerOutputBalanceBefore"] == -fee
        cases.append({"recipient": recipient, "initialPayerOutputBalance": execution["payerOutputBalanceBefore"],
                      "recipientOutputBalanceBefore": execution["recipientOutputBalanceBefore"],
                      "recipientOutputBalanceAfter": execution["recipientOutputBalanceAfter"],
                      "payerOutputBalanceAfter": execution["payerOutputBalanceAfter"],
                      "hookQuote": result["candidate"]["amountOut"],
                      "grossOutputTransfer": execution["grossOutputTransfer"],
                      "recipientDelta": execution["recipientDelta"],
                      "feeToken": execution["feeToken"], "feePayer": execution["feePayer"],
                      "feeTokenTransfers": execution["feeTokenTransfers"],
                      "gasUsed": execution["gasUsed"],
                      "effectiveGasPrice": execution["effectiveGasPrice"],
                      "expectedFeeRawFromGas": expected_fee,
                      "nativeGasBalanceBefore": execution["payerNativeBalanceBeforeExecution"],
                      "nativeGasBalanceAfter": execution["payerNativeBalanceAfterExecution"],
                      "testFunding": result["testFunding"]})
    report = {"chainId": HISTORICAL_CONTEXT.chain_id, "blockNumber": HISTORICAL_CONTEXT.number,
              "blockHash": HISTORICAL_CONTEXT.hash, "amountInRawCUSD": 1_000_000,
              "recipientCases": cases}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
