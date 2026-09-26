"""Route-level quote dispatch boundary for the verified Tempo v4 scope.

The normal-quoter and full-transaction validator are replaceable adapters.
Boundary mocks can test routing decisions; only a real fork validator proves
Universal Router execution. No result enters comparison until validated.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    return {"status": "success", "amountOut": execution["grossOutputTransfer"],
            "recipientDelta": execution["recipientDelta"],
            "gasUsed": execution["gasUsed"], "hookCalls": execution["hookCalls"]}


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
        is_tempo = any(hop.pool_key.hooks.lower() == HOOK for hop in request.route.hops)
        try:
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
        except Exception as exc:
            outcome.update(validationStatus="failed", validationError=str(exc))
            continue

        outcome["validationStatus"] = "validated"
        outcome["gasUsed"] = validation.get("gasUsed")
        comparison.append({"routeId": request.route_id, "route": request.route.label,
                           "amountIn": request.amount_in, "amountOut": amount_out,
                           "quotePath": outcome["quotePath"],
                           "gasUsed": validation.get("gasUsed"),
                           "validationStatus": "validated"})
    return {"outcomes": outcomes, "comparisonInput": comparison}
