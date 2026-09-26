"""Produce one dashboard record from one snapshotted Tempo fork run."""

from __future__ import annotations

import argparse
import json
import sys

from quote_dispatch import plan_digest, reconcile_execution_output
from tempo_quote import (HISTORICAL_CONTEXT, TOKENS, RpcError, TempoClient,
                         UnsupportedRoute, run_fork_case)


CASES = {
    "small": 1_000_000,
    "gap": 25_000_000,
    "illiquid": 1_000_000_000_000,
}
LIQUIDITY_SELECTOR = "0xbb55fd27"


def short_error(value: object) -> str:
    message = str(value or "Unknown error")
    if LIQUIDITY_SELECTOR in message.lower() or "insufficientliquidity" in message.lower():
        return "InsufficientLiquidity()"
    if "execution reverted" in message:
        return "Contract call reverted"
    return message[:180]


def build_record(case_id: str, result: dict) -> dict:
    """Project measured fork data into a bounded, browser-facing record."""
    if case_id not in CASES or result["amountIn"] != CASES[case_id]:
        raise ValueError("case ID and measured input amount do not match")
    if (result["chainId"], result["parentBlock"], result["blockHash"].lower()) != (
        HISTORICAL_CONTEXT.chain_id, HISTORICAL_CONTEXT.number,
        HISTORICAL_CONTEXT.hash.lower()
    ):
        raise ValueError("fork result is not from the verified block")

    baseline = result["standardQuote"]
    candidate = result["candidate"]
    execution = result["execution"]
    plan = result.get("plan")
    manager_balance = result["poolManagerInputBalance"]
    baseline_stage = None
    if baseline["status"] == "revert":
        if case_id == "gap" and result["amountIn"] > manager_balance:
            baseline_stage = "PoolManager.take(cUSD)"
        else:
            baseline_stage = "V4Quoter call"
    baseline_view = {
        "status": baseline["status"],
        "amountOutRaw": baseline.get("amountOut"),
        "errorStage": baseline_stage,
        "error": short_error(baseline.get("error")) if baseline_stage else None,
    }

    quote_status = candidate["status"]
    quote_view = {
        "status": quote_status,
        "amountOutRaw": candidate.get("amountOut"),
        "hops": [{"source": hop["source"], "target": hop["target"],
                  "amountInRaw": hop["amountIn"], "amountOutRaw": hop["amountOut"]}
                 for hop in candidate.get("hops", [])],
        "errorStage": None,
        "error": None,
    }
    if quote_status != "candidate":
        quote_view["error"] = short_error(candidate.get("error"))
        quote_view["errorStage"] = (
            "Tempo Exchange liquidity" if quote_view["error"] == "InsufficientLiquidity()"
            else "Tempo hook quote"
        )

    plan_view = ({"status": "diagnostic" if plan.get("diagnosticOnly") else "built",
                  "actions": plan["actions"],
                  "minimumOutputRaw": plan["minimumOutput"],
                  "planDigest": plan_digest(plan)} if plan else
                 {"status": "not-built", "actions": [],
                  "minimumOutputRaw": None, "planDigest": None})
    execution_view = {
        "status": execution["status"],
        "receiptStatus": execution.get("receiptStatus", 1 if execution["status"] == "success" else None),
        "recipientDeltaRaw": execution.get("recipientDelta"),
        "grossOutputRaw": execution.get("grossOutputTransfer"),
        "gasUsed": execution.get("gasUsed"),
        "hookCalls": execution.get("hookCalls"),
        "localForkTxHash": execution.get("localForkTxHash"),
        "errorStage": execution.get("phase"),
        "error": short_error(execution.get("error")) if execution.get("error") else None,
    }

    comparison = {"status": "not-comparable", "deltaRaw": None,
                  "toleranceRaw": 0, "reason": "A quote and funded execution are both required"}
    if quote_status == "candidate" and execution["status"] == "success" and plan:
        recovered = candidate["amountOut"]
        received = execution["recipientDelta"]
        delta = received - recovered
        reconciliation = reconcile_execution_output(
            execution, plan, TOKENS["USDT0"], recovered)
        if delta == 0 and reconciliation["status"] == "success":
            comparison = {"status": "matched", "deltaRaw": 0,
                          "toleranceRaw": 0,
                          "reason": "Recipient balance change equals the recovered quote"}
        else:
            comparison = {"status": "mismatch" if reconciliation["status"] == "failed"
                          or delta != 0 else "indeterminate",
                          "deltaRaw": delta, "toleranceRaw": 0,
                          "reason": reconciliation.get("reason", "Recipient output differs from quote")}
    elif quote_status != "candidate":
        comparison["reason"] = "QuoteBridge could not produce a candidate"
    elif execution["status"] == "revert":
        comparison["reason"] = "The funded Router transaction reverted"

    return {
        "caseId": case_id,
        "chainId": result["chainId"],
        "blockNumber": result["parentBlock"],
        "blockHash": result["blockHash"],
        "route": result["route"],
        "amountInRaw": result["amountIn"],
        "poolManagerInputBalanceRaw": manager_balance,
        "payerInputBalanceBeforeFundingRaw": result["payerInputBalanceBeforeFunding"],
        "testFunding": result["testFunding"],
        "baseline": baseline_view,
        "quoteBridge": quote_view,
        "plan": plan_view,
        "execution": execution_view,
        "comparison": comparison,
        "whyThisMatters": (baseline["status"] == "revert"
                           and quote_status == "candidate"
                           and execution["status"] == "success"
                           and comparison["status"] == "matched"),
        "snapshotReverted": True,
        "rpcCalls": result["metrics"]["rpcCalls"],
        "elapsedMs": result["metrics"]["elapsedMs"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    try:
        result = run_fork_case(TempoClient(args.rpc), "cUSD", "USDT0",
                               CASES[args.case], probe_illiquidity=args.case == "illiquid")
        print(json.dumps(build_record(args.case, result)))
    except (RpcError, UnsupportedRoute, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
