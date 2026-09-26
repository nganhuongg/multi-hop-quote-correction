"""Dispatch-boundary tests; the ordinary quoter and validator are explicit mocks."""

import unittest
from dataclasses import replace

from quote_dispatch import RouteRequest, dispatch_quotes, plan_digest, route_key
from tempo_quote import (FEE, HISTORICAL_CONTEXT, TICK_SPACING, TOKENS,
                         Hop, PoolKey, RouteDescription, RpcError, resolve_route)


TEMPO_ROUTE = resolve_route("cUSD", "USDT0")
ORDINARY_ROUTE = RouteDescription(
    "cUSD", "USDT0",
    (Hop("cUSD", "USDT0",
         PoolKey(TOKENS["cUSD"], TOKENS["USDT0"], FEE, TICK_SPACING,
                 "0x" + "00" * 20, "0x" + "ab" * 32), True),),
)


class HookClient:
    def __init__(self, outputs=(24_995_000, 24_997_499), error=None):
        self.outputs = iter(outputs)
        self.error = error
        self.count = 0
        self.tags = []

    def pinned_block(self, context):
        self.tags.append(context.tag)

    def selector(self, signature):
        self.count += 1
        return "0x12345678"

    def rpc(self, method, params):
        self.count += 1
        self.tags.append(params[1])
        if self.error:
            raise RpcError(self.error)
        return hex(next(self.outputs))


def accepted_tempo_validation(request, quote, context):
    plan = {"to": "0xrouter", "from": "0xpayer", "data": "0x1234",
            "value": "0x0", "payer": "0xpayer", "recipient": "0xpayer",
            "deadline": 1790346234, "minimumOutput": 24_872_511}
    return {"status": "success", "amountOut": quote["amountOut"],
            "recipientDelta": quote["amountOut"], "gasUsed": 320_000,
            "routeKey": route_key(request.route), "amountIn": request.amount_in,
            "chainId": context.chain_id, "blockNumber": context.number,
            "blockHash": context.hash, "executionPlan": plan,
            "planDigest": plan_digest(plan)}


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tempo = RouteRequest("tempo-two-hop", TEMPO_ROUTE, 25_000_000)
        self.ordinary = RouteRequest("ordinary", ORDINARY_ROUTE, 25_000_000)

    def test_recovered_route_reaches_comparison_with_standard_candidate(self):
        client = HookClient()
        standard_calls = []
        validation_calls = []

        def normal(route, amount, context):
            standard_calls.append((route, amount, context))
            return {"status": "success", "amountOut": 24_000_000}

        def validate(request, quote, context):
            validation_calls.append((request.route_id, context))
            if request.route_id == "tempo-two-hop":
                return accepted_tempo_validation(request, quote, context)
            return {"status": "success", "amountOut": quote["amountOut"],
                    "gasUsed": 320_000}

        batch = dispatch_quotes(client, [self.tempo, self.ordinary],
                                HISTORICAL_CONTEXT, normal, validate)
        self.assertEqual([q["routeId"] for q in batch["comparisonInput"]],
                         ["tempo-two-hop", "ordinary"])
        self.assertEqual([q["amountOut"] for q in batch["comparisonInput"]],
                         [24_997_499, 24_000_000])
        self.assertEqual([o["quotePath"] for o in batch["outcomes"]],
                         ["tempo_hook", "standard"])
        self.assertEqual([o["validationStatus"] for o in batch["outcomes"]],
                         ["validated", "validated"])
        self.assertEqual(standard_calls, [(ORDINARY_ROUTE, 25_000_000, HISTORICAL_CONTEXT)])
        self.assertEqual(validation_calls,
                         [("tempo-two-hop", HISTORICAL_CONTEXT),
                          ("ordinary", HISTORICAL_CONTEXT)])
        self.assertEqual(client.tags, [HISTORICAL_CONTEXT.tag] * 3)

    def test_candidate_without_execution_is_not_compared(self):
        batch = dispatch_quotes(HookClient(), [self.tempo], HISTORICAL_CONTEXT)
        self.assertEqual(batch["outcomes"][0]["quoteStatus"], "candidate")
        self.assertEqual(batch["outcomes"][0]["validationStatus"], "not_checked")
        self.assertEqual(batch["comparisonInput"], [])

    def test_real_liquidity_error_remains_a_failed_quote(self):
        batch = dispatch_quotes(HookClient(error="InsufficientLiquidity()"),
                                [self.tempo], HISTORICAL_CONTEXT)
        outcome = batch["outcomes"][0]
        self.assertEqual(outcome["quoteStatus"], "failed")
        self.assertIn("InsufficientLiquidity", outcome["quoteError"])
        self.assertEqual(batch["comparisonInput"], [])

    def test_unsupported_tempo_route_is_not_sent_to_standard_quoter(self):
        bad_key = replace(TEMPO_ROUTE.hops[0].pool_key, pool_id="0x" + "ff" * 32)
        bad_route = replace(TEMPO_ROUTE, hops=(replace(TEMPO_ROUTE.hops[0], pool_key=bad_key),
                                               TEMPO_ROUTE.hops[1]))
        called = []
        batch = dispatch_quotes(HookClient(), [replace(self.tempo, route=bad_route)],
                                HISTORICAL_CONTEXT,
                                lambda *args: called.append(args))
        self.assertEqual(batch["outcomes"][0]["quoteStatus"], "unsupported")
        self.assertEqual(called, [])
        self.assertEqual(batch["comparisonInput"], [])

    def test_ordinary_failure_stays_on_standard_path(self):
        client = HookClient()
        batch = dispatch_quotes(client, [self.ordinary], HISTORICAL_CONTEXT,
                                lambda *_: {"status": "revert", "error": "NotEnoughLiquidity"})
        outcome = batch["outcomes"][0]
        self.assertEqual(outcome["quotePath"], "standard")
        self.assertEqual(outcome["quoteStatus"], "failed")
        self.assertIn("NotEnoughLiquidity", outcome["quoteError"])
        self.assertEqual(client.tags, [])

    def test_unknown_custom_hook_is_explicitly_rejected(self):
        bad_key = replace(ORDINARY_ROUTE.hops[0].pool_key,
                          hooks="0x" + "11" * 20)
        route = replace(ORDINARY_ROUTE,
                        hops=(replace(ORDINARY_ROUTE.hops[0], pool_key=bad_key),))
        batch = dispatch_quotes(HookClient(), [replace(self.ordinary, route=route)],
                                HISTORICAL_CONTEXT,
                                lambda *_: self.fail("unverified hook reached standard quoter"))
        self.assertEqual(batch["outcomes"][0]["quoteStatus"], "unsupported")
        self.assertIn("unverified hook", batch["outcomes"][0]["quoteError"])
        self.assertEqual(batch["comparisonInput"], [])

    def test_validation_mismatch_keeps_candidate_out_of_comparison(self):
        batch = dispatch_quotes(HookClient(), [self.tempo], HISTORICAL_CONTEXT,
                                validator=lambda *_: {"status": "success", "amountOut": 1})
        self.assertEqual(batch["outcomes"][0]["quoteStatus"], "candidate")
        self.assertEqual(batch["outcomes"][0]["validationStatus"], "failed")
        self.assertEqual(batch["comparisonInput"], [])

    def test_execution_failure_and_unavailable_validation_are_ineligible(self):
        for validator in (None, lambda *_: {"status": "failed", "reason": "router revert"}):
            batch = dispatch_quotes(HookClient(), [self.tempo], HISTORICAL_CONTEXT,
                                    validator=validator)
            self.assertEqual(batch["comparisonInput"], [])
            self.assertEqual(batch["outcomes"][0]["quoteStatus"], "candidate")

    def test_validation_must_bind_route_amount_block_and_plan(self):
        invalid = ({"routeKey": "another route"}, {"amountIn": 1},
                   {"blockNumber": HISTORICAL_CONTEXT.number + 1},
                   {"blockHash": "0xdead"}, {"planDigest": "another plan"},
                   {"recipientDelta": 24_997_498})
        for override in invalid:
            def validate(request, quote, context):
                return accepted_tempo_validation(request, quote, context) | override
            batch = dispatch_quotes(HookClient(), [self.tempo], HISTORICAL_CONTEXT,
                                    validator=validate)
            self.assertEqual(batch["comparisonInput"], [], override)
            self.assertEqual(batch["outcomes"][0]["validationStatus"], "failed")


if __name__ == "__main__":
    unittest.main()
