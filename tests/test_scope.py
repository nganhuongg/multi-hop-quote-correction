"""Scope and encoding checks; these are not evidence of Tempo execution."""

import unittest
from dataclasses import replace

from tempo_quote import (BLOCK, HISTORICAL_CONTEXT, BlockContext,
                         UnsupportedRoute, build_plan, quote_candidate,
                         resolve_route, validate_supported_route)


class ScopeTests(unittest.TestCase):
    def test_unsupported_routes_are_explicit(self):
        for pair in (("USDT0", "cUSD"), ("cUSD", "cUSD"),
                     ("PathUSD", "USDT0"), ("USDC.e", "USDT0")):
            with self.assertRaises(UnsupportedRoute):
                resolve_route(*pair)

    def test_supported_route_has_verified_pool_ids_and_direction(self):
        hops = resolve_route("cUSD", "USDT0").hops
        self.assertEqual(len(hops), 2)
        self.assertFalse(hops[0].zero_for_one)
        self.assertTrue(hops[1].zero_for_one)
        self.assertEqual(hops[0].pool_id, "0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57")
        self.assertEqual(hops[1].pool_id, "0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22")

    def test_unverified_block_is_rejected_before_any_rpc(self):
        with self.assertRaises(UnsupportedRoute):
            quote_candidate(None, resolve_route("cUSD", "USDT0"), 1_000_000,
                            BlockContext(4217, BLOCK + 1, HISTORICAL_CONTEXT.hash))

    def test_execution_plan_rejects_unverified_candidate(self):
        candidate = {"status": "candidate", "source": "cUSD", "target": "USDT0",
                     "amountIn": 1_000_000, "block": 0,
                     "blockHash": "0x0", "hook": "0x0"}
        with self.assertRaises(UnsupportedRoute):
            build_plan(candidate, resolve_route("cUSD", "USDT0"), 1_000_000,
                       HISTORICAL_CONTEXT, "0x" + "11" * 20,
                       "0x" + "11" * 20, 1)

    def test_route_key_direction_and_continuity_are_checked(self):
        route = resolve_route("cUSD", "USDT0")
        bad_key = replace(route.hops[0].pool_key, hooks="0x" + "11" * 20)
        changes = (
            replace(route.hops[0], pool_key=bad_key),
            replace(route.hops[0], zero_for_one=True),
            replace(route.hops[0], target="USDT0"),
        )
        for changed in changes:
            with self.assertRaises(UnsupportedRoute):
                validate_supported_route(replace(route, hops=(changed, route.hops[1])),
                                         HISTORICAL_CONTEXT)

    def test_every_hook_quote_uses_the_same_block_tag(self):
        class RecordingClient:
            count = 0

            def __init__(self):
                self.tags = []

            def pinned_block(self, context):
                self.tags.append(context.tag)

            def selector(self, signature):
                self.count += 1
                return "0x12345678"

            def rpc(self, method, params):
                self.count += 1
                self.tags.append(params[1])
                return hex(900_000 if len(self.tags) == 2 else 800_000)

        client = RecordingClient()
        result = quote_candidate(client, resolve_route("cUSD", "USDT0"),
                                 1_000_000, HISTORICAL_CONTEXT)
        self.assertEqual(client.tags, [HISTORICAL_CONTEXT.tag] * 3)
        self.assertEqual(result["hops"][1]["amountIn"], 900_000)
        self.assertEqual(result["amountOut"], 800_000)


if __name__ == "__main__":
    unittest.main()
