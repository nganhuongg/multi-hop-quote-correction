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

from tempo_quote import (HOOK, BlockContext, RouteDescription, TempoClient,
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


def validate_tempo_on_fork(client: TempoClient, request: RouteRequest,
                           candidate: dict, context: BlockContext) -> dict:
    """Validate one specialized candidate with deployed contracts on Anvil."""
    result = run_fork_route_case(client, request.route, request.amount_in, context)
    execution = result["execution"]
    if result["candidate"].get("amountOut") != candidate["amountOut"]:
        return {"status": "failed", "reason": "candidate changed before execution"}
    if execution["status"] != "success":
        return {"status": "failed", "reason": execution.get("error", execution["status"])}
    if (execution["grossOutputTransfer"] != candidate["amountOut"]
            or not execution["matchesQuote"]):
        return {"status": "failed", "reason": "full-router gross output differs from candidate"}
    if execution["recipientDelta"] != candidate["amountOut"]:
        return {"status": "failed", "reason": "recipient balance delta differs from candidate"}
    return {"status": "success", "amountOut": execution["grossOutputTransfer"],
            "recipientDelta": execution["recipientDelta"],
            "gasUsed": execution["gasUsed"], "hookCalls": execution["hookCalls"],
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
                        or validation.get("recipientDelta") != amount_out
                        or validation.get("planDigest") != plan_digest(validation.get("executionPlan", {}))):
                    raise ValueError("execution validation is not bound to route, amount, block and plan")
        except Exception as exc:
            outcome.update(validationStatus="failed", validationError=str(exc))
            continue

        outcome["validationStatus"] = "validated"
        outcome["gasUsed"] = validation.get("gasUsed")
        if outcome["quotePath"] == "tempo_hook":
            outcome["planDigest"] = validation["planDigest"]
        entry = {"routeId": request.route_id, "route": request.route.label,
                 "amountIn": request.amount_in, "amountOut": amount_out,
                 "quotePath": outcome["quotePath"],
                 "gasUsed": validation.get("gasUsed"),
                 "validationStatus": "validated"}
        if outcome["quotePath"] == "tempo_hook":
            entry["planDigest"] = validation["planDigest"]
        comparison.append(entry)
    return {"outcomes": outcomes, "comparisonInput": comparison}
