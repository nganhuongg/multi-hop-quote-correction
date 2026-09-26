"""Scope and encoding checks; these are not evidence of Tempo execution."""

import unittest

from tempo_quote import UnsupportedRoute, build_plan, quote_candidate, resolve_route


class ScopeTests(unittest.TestCase):
    def test_unsupported_routes_are_explicit(self):
        for pair in (("USDT0", "cUSD"), ("cUSD", "cUSD"),
                     ("PathUSD", "USDT0"), ("USDC.e", "USDT0")):
            with self.assertRaises(UnsupportedRoute):
                resolve_route(*pair)

    def test_supported_route_has_verified_pool_ids_and_direction(self):
        hops = resolve_route("cUSD", "USDT0")
        self.assertEqual(len(hops), 2)
        self.assertFalse(hops[0].zero_for_one)
        self.assertTrue(hops[1].zero_for_one)
        self.assertEqual(hops[0].pool_id, "0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57")
        self.assertEqual(hops[1].pool_id, "0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22")

    def test_unverified_block_is_rejected_before_any_rpc(self):
        with self.assertRaises(UnsupportedRoute):
            quote_candidate(None, "cUSD", "USDT0", 1_000_000, block=41_183_157)

    def test_execution_plan_rejects_unverified_candidate(self):
        candidate = {"status": "candidate", "source": "cUSD", "target": "USDT0",
                     "block": 0, "blockHash": "0x0", "hook": "0x0"}
        with self.assertRaises(UnsupportedRoute):
            build_plan(candidate, "0x" + "11" * 20, "0x" + "11" * 20, 1)


if __name__ == "__main__":
    unittest.main()
