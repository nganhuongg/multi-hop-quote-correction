"""Route-level quote dispatch boundary for the verified Tempo v4 scope.

The normal-quoter and full-transaction validator are replaceable adapters.
Boundary mocks can test routing decisions; only a real fork validator proves
Universal Router execution. No result enters comparison until validated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Callable

from tempo_quote import (HOOK, MANAGER, TOKENS, BlockContext, RouteDescription, TempoClient,
                         UnsupportedRoute, quote_candidate,
                         run_fork_route_case, standard_quote,
                         validate_route_continuity, validate_supported_route)


@dataclass(frozen=True)
class RouteRequest:
    route_id: str
    route: RouteDescription
    amount_in: int


StandardQuoter = Callable[[RouteDescription, int, BlockContext], dict]
FullValidator = Callable[[RouteRequest, dict, BlockContext], dict]
TEMPO_FEE_COLLECTOR = "0xfeec000000000000000000000000000000000000"


def route_key(route: RouteDescription) -> str:
    """Bind an admission to the complete route, including pool keys and hook data."""
    return hashlib.sha256(json.dumps(asdict(route), sort_keys=True).encode()).hexdigest()


def plan_digest(plan: dict) -> str:
    """Bind validation to the complete execution plan, including calldata."""
    fields = ("to", "from", "data", "value", "payer", "recipient",
              "deadline", "minimumOutput")
    if any(field not in plan for field in fields):
        raise ValueError("validation omitted executable plan fields")
    return hashlib.sha256(json.dumps({field: plan[field] for field in fields},
                                     sort_keys=True).encode()).hexdigest()


def reconcile_execution_output(execution: dict, plan: dict,
                               output_token: str, quoted_amount: int) -> dict:
    """Separate the executed swap transfer from gas paid by its recipient.

    The receipt must show one PoolManager output transfer. A recipient-paid
    output-token gas charge is restored only when the receipt identifies the
    payer/token and shows one actual transfer to Tempo's observed fee collector.
    Unexplained balance movements make validation indeterminate.
    """
    recipient = plan["recipient"].lower()
    transfers = execution.get("outputTokenTransfers")
    if not isinstance(transfers, list):
        return {"status": "indeterminate", "reason": "executed output transfer logs unavailable"}
    if any(not isinstance(item, dict) for item in transfers):
        return {"status": "indeterminate", "reason": "executed output transfer logs malformed"}
    swap_transfers = [item for item in transfers
                      if str(item.get("from", "")).lower() == MANAGER.lower()
                      and str(item.get("to", "")).lower() == recipient]
    if len(swap_transfers) != 1 or not isinstance(swap_transfers[0].get("amount"), int):
        return {"status": "indeterminate", "reason": "executed swap output transfer is ambiguous"}
    swap_output = swap_transfers[0]["amount"]
    if swap_output != quoted_amount:
        return {"status": "failed", "reason": "executed swap output differs from candidate"}
    if execution.get("grossOutputTransfer") != swap_output:
        return {"status": "indeterminate", "reason": "preflight and executed output transfers differ"}
    balance_delta = execution.get("recipientDelta")
    if not isinstance(balance_delta, int):
        return {"status": "indeterminate", "reason": "recipient balance delta unavailable"}

    fee_paid_in_output = 0
    if (str(execution.get("feePayer", "")).lower() == recipient
            and str(execution.get("feeToken", "")).lower() == output_token.lower()):
        fee_transfers = execution.get("feeTokenTransfers")
        if not isinstance(fee_transfers, list) or len(fee_transfers) != 1:
            return {"status": "indeterminate", "reason": "recipient gas payment is not isolated"}
        transfer = fee_transfers[0]
        if (not isinstance(transfer, dict)
                or str(transfer.get("from", "")).lower() != recipient
                or str(transfer.get("to", "")).lower() != TEMPO_FEE_COLLECTOR
                or not isinstance(transfer.get("amount"), int)
                or transfer["amount"] <= 0):
            return {"status": "indeterminate", "reason": "recipient gas payment is not proven"}
        fee_paid_in_output = transfer["amount"]

    recipient_swap_output = balance_delta + fee_paid_in_output
    if recipient_swap_output != swap_output:
        return {"status": "indeterminate", "reason": "recipient token flows do not reconcile"}
    return {"status": "success", "recipientSwapOutput": recipient_swap_output,
            "recipientDelta": balance_delta,
            "gasPaidInOutputByRecipient": fee_paid_in_output}


def validate_tempo_on_fork(client: TempoClient, request: RouteRequest,
                           candidate: dict, context: BlockContext) -> dict:
    """Validate one specialized candidate with deployed contracts on Anvil."""
    result = run_fork_route_case(client, request.route, request.amount_in, context)
    execution = result["execution"]
    if result["candidate"].get("amountOut") != candidate["amountOut"]:
        return {"status": "failed", "reason": "candidate changed before execution"}
    if execution["status"] != "success":
        return {"status": "failed", "reason": execution.get("error", execution["status"])}
    reconciled = reconcile_execution_output(
        execution, result["plan"], TOKENS[request.route.target], candidate["amountOut"])
    if reconciled["status"] != "success":
        return reconciled
    return {"status": "success", "amountOut": execution["grossOutputTransfer"],
            **reconciled,
            "gasUsed": execution["gasUsed"], "hookCalls": execution["hookCalls"],
            "localForkTxHash": execution["localForkTxHash"],
            "routeKey": route_key(request.route), "amountIn": request.amount_in,
            "chainId": context.chain_id, "blockNumber": context.number,
            "blockHash": context.hash, "executionPlan": result["plan"],
            "planDigest": plan_digest(result["plan"])}


def dispatch_quotes(client: TempoClient, requests: list[RouteRequest],
                    context: BlockContext, standard_quoter: StandardQuoter | None = None,
                    validator: FullValidator | None = None) -> dict:
    """Quote one trade's candidate routes and return a validated comparison input.

    A known Tempo hook with an unverified structure is rejected. Other routes
    keep the standard quote path; their failures never trigger a Tempo fallback.
    The caller must supply a full-transaction validator before comparison.
    """
    if not requests:
        return {"outcomes": [], "comparisonInput": []}
    trade = (requests[0].route.source, requests[0].route.target, requests[0].amount_in)
    if any((item.route.source, item.route.target, item.amount_in) != trade for item in requests):
        raise ValueError("comparison candidates must share input token, output token, and raw amount")

    normal_quote = standard_quoter or (
        lambda route, amount, block: standard_quote(client, route, amount, block)
    )
    outcomes: list[dict] = []
    comparison: list[dict] = []
    for request in requests:
        outcome = {"routeId": request.route_id, "route": request.route.label,
                   "quotePath": None, "quoteStatus": "not_attempted",
                   "validationStatus": "not_attempted", "amountOut": None,
                   "quoteError": None, "validationError": None}
        outcomes.append(outcome)
        try:
            hooks = [hop.pool_key.hooks.lower() for hop in request.route.hops]
            is_tempo = HOOK in hooks
            if any(hook not in (HOOK, "0x" + "00" * 20) for hook in hooks):
                raise UnsupportedRoute("unverified hook deployment")
            if is_tempo:
                outcome["quotePath"] = "tempo_hook"
                validate_supported_route(request.route, context)
                quote = quote_candidate(client, request.route, request.amount_in, context)
                amount_out = quote["amountOut"]
            else:
                outcome["quotePath"] = "standard"
                validate_route_continuity(request.route)
                quote = normal_quote(request.route, request.amount_in, context)
                if quote.get("status") != "success":
                    raise RuntimeError(quote.get("error", "standard quote failed"))
                amount_out = quote["amountOut"]
            if not isinstance(amount_out, int) or amount_out <= 0:
                raise ValueError("quoter returned no positive output")
        except UnsupportedRoute as exc:
            outcome.update(quoteStatus="unsupported", quoteError=str(exc))
            continue
        except Exception as exc:
            outcome.update(quoteStatus="failed", quoteError=str(exc))
            continue

        outcome.update(quoteStatus="candidate", amountOut=amount_out,
                       validationStatus="not_checked")
        if validator is None:
            continue
        try:
            validation = validator(request, quote, context)
            if validation.get("status") == "indeterminate":
                outcome.update(validationStatus="indeterminate",
                               validationError=validation.get("reason", "token flows could not be separated"))
                continue
            if validation.get("status") != "success":
                raise RuntimeError(validation.get("reason", "execution failed"))
            if validation.get("amountOut") != amount_out:
                raise ValueError("validated output differs from candidate quote")
            if outcome["quotePath"] == "tempo_hook":
                if (validation.get("routeKey") != route_key(request.route)
                        or validation.get("amountIn") != request.amount_in
                        or validation.get("chainId") != context.chain_id
                        or validation.get("blockNumber") != context.number
                        or validation.get("blockHash", "").lower() != context.hash.lower()
                        or validation.get("recipientSwapOutput") != amount_out
                        or validation.get("planDigest") != plan_digest(validation.get("executionPlan", {}))):
                    raise ValueError("execution validation is not bound to route, amount, block and plan")
        except Exception as exc:
            outcome.update(validationStatus="failed", validationError=str(exc))
            continue

        outcome["validationStatus"] = "validated"
        outcome["gasUsed"] = validation.get("gasUsed")
        if outcome["quotePath"] == "tempo_hook":
            outcome["planDigest"] = validation["planDigest"]
            outcome["recipientDelta"] = validation["recipientDelta"]
            outcome["gasPaidInOutputByRecipient"] = validation["gasPaidInOutputByRecipient"]
            outcome["hookCalls"] = validation.get("hookCalls")
            outcome["localForkTxHash"] = validation.get("localForkTxHash")
        entry = {"routeId": request.route_id, "route": request.route.label,
                 "amountIn": request.amount_in, "amountOut": amount_out,
                 "quotePath": outcome["quotePath"],
                 "gasUsed": validation.get("gasUsed"),
                 "validationStatus": "validated"}
        if outcome["quotePath"] == "tempo_hook":
            entry["planDigest"] = validation["planDigest"]
            entry["recipientDelta"] = validation["recipientDelta"]
            entry["gasPaidInOutputByRecipient"] = validation["gasPaidInOutputByRecipient"]
            entry["hookCalls"] = validation.get("hookCalls")
            entry["localForkTxHash"] = validation.get("localForkTxHash")
        comparison.append(entry)
    return {"outcomes": outcomes, "comparisonInput": comparison}
