"""Real-contract regression. Run only against a fresh local Tempo Anvil fork.

TEMPO_FORK_RPC must point at Anvil forked at block 41183156. No call here is
sent to Tempo mainnet. The implementation under test snapshots and reverts the
fork; only the test payer is funded. PoolManager and Tempo Exchange are not.
"""

import os
import unittest

from tempo_quote import TempoClient, run_fork_case


@unittest.skipUnless(os.getenv("TEMPO_FORK_RPC"), "set TEMPO_FORK_RPC to a local Anvil fork")
class RealTempoForkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TempoClient(os.environ["TEMPO_FORK_RPC"])

    def test_restores_missing_quote_and_executes_full_router_transaction(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 25_000_000)
        self.assertEqual(result["parentBlock"], 41_183_156)
        self.assertEqual(result["poolManagerInputBalance"], 19_862_459)
        self.assertEqual(result["standardQuote"]["status"], "revert")
        self.assertEqual(result["candidate"]["amountOut"], 24_997_499)
        self.assertEqual(result["execution"]["status"], "success")
        self.assertEqual(result["execution"]["recipientDelta"], 24_997_499)
        self.assertTrue(result["execution"]["matchesQuote"])
        self.assertEqual(result["execution"]["hookCalls"], 2)

    def test_small_multihop_control(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 1_000_000)
        self.assertEqual(result["standardQuote"]["amountOut"], 999_899)
        self.assertEqual(result["candidate"]["amountOut"], 999_899)
        self.assertEqual(result["execution"]["recipientDelta"], 999_899)

    def test_single_hop_control(self):
        result = run_fork_case(self.client, "cUSD", "PathUSD", 1_000_000)
        self.assertEqual(result["candidate"]["amountOut"], 999_800)
        self.assertEqual(result["execution"]["recipientDelta"], 999_800)

    def test_real_exchange_illiquidity_is_rejected(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 1_000_000_000_000)
        self.assertEqual(result["candidate"]["status"], "revert")
        self.assertEqual(result["execution"]["status"], "not-attempted")


if __name__ == "__main__":
    unittest.main()
