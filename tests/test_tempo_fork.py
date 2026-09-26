"""Real-contract regression. Run only against a fresh local Tempo Anvil fork.

TEMPO_FORK_RPC must point at Anvil forked at block 41183156. No call here is
sent to Tempo mainnet. The implementation under test snapshots and reverts the
fork; only the test payer is funded. PoolManager and Tempo Exchange are not.
"""

import os
import unittest

from tempo_quote import PAYER, TOKENS, TempoClient, run_fork_case
from tempo_quote import HISTORICAL_CONTEXT, resolve_route
from quote_dispatch import (RouteRequest, dispatch_quotes,
                            reconcile_execution_output, validate_tempo_on_fork)


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
        self.assertEqual(result["candidate"]["blockHash"], "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3")
        self.assertEqual(result["plan"]["actions"], ["SETTLE", "SWAP_EXACT_IN", "TAKE"])
        self.assertEqual(result["plan"]["minimumOutput"], 24_872_511)
        self.assertTrue(result["plan"]["data"].startswith("0x"))
        self.assertEqual(result["execution"]["status"], "success")
        self.assertEqual(result["execution"]["grossOutputTransfer"], 24_997_499)
        self.assertEqual(result["execution"]["recipientDelta"], 24_997_499)
        self.assertTrue(result["execution"]["matchesQuote"])
        self.assertEqual(result["execution"]["hookCalls"], 2)

    def test_small_multihop_control(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 1_000_000)
        self.assertEqual(result["standardQuote"]["amountOut"], 999_899)
        self.assertEqual(result["candidate"]["amountOut"], 999_899)
        self.assertEqual(result["execution"]["recipientDelta"], 999_899)

    def test_other_supported_multihop_target(self):
        result = run_fork_case(self.client, "cUSD", "USDC.e", 1_000_000)
        self.assertEqual(result["standardQuote"]["amountOut"], 999_800)
        self.assertEqual(result["candidate"]["amountOut"], 999_800)
        self.assertEqual(result["execution"]["recipientDelta"], 999_800)

    def test_single_hop_control(self):
        result = run_fork_case(self.client, "cUSD", "PathUSD", 1_000_000)
        self.assertEqual(result["candidate"]["amountOut"], 999_800)
        self.assertEqual(result["execution"]["grossOutputTransfer"], 999_800)
        self.assertTrue(result["execution"]["matchesQuote"])
        execution = result["execution"]
        self.assertEqual(execution["recipientDelta"], 999_479)
        self.assertEqual(execution["payerOutputBalanceBefore"], 39_805)
        self.assertEqual(execution["payerOutputBalanceAfter"], 1_039_284)
        self.assertEqual(execution["feeToken"].lower(), TOKENS["PathUSD"].lower())
        self.assertEqual(execution["feePayer"].lower(), PAYER.lower())
        self.assertEqual(sum(log["amount"] for log in execution["feeTokenTransfers"]), 321)
        self.assertEqual(execution["recipientDelta"] + 321, result["candidate"]["amountOut"])

    def test_separate_recipient_gets_gross_output_while_payer_pays_pathusd_gas(self):
        recipient = "0x1111111111111111111111111111111111111111"
        result = run_fork_case(self.client, "cUSD", "PathUSD", 1_000_000,
                               recipient=recipient)
        execution = result["execution"]
        self.assertEqual(execution["grossOutputTransfer"], 999_800)
        self.assertEqual(execution["recipientOutputBalanceBefore"], 2_500)
        self.assertEqual(execution["recipientOutputBalanceAfter"], 1_002_300)
        self.assertEqual(execution["recipientDelta"], 999_800)
        self.assertEqual(execution["payerOutputBalanceBefore"], 39_805)
        self.assertEqual(execution["payerOutputBalanceAfter"], 39_473)
        self.assertEqual(sum(log["amount"] for log in execution["feeTokenTransfers"]), 332)
        reconciled = reconcile_execution_output(
            execution, result["plan"], TOKENS["PathUSD"], result["candidate"]["amountOut"])
        self.assertEqual(reconciled["status"], "success")
        self.assertEqual(reconciled["recipientSwapOutput"], 999_800)
        self.assertEqual(reconciled["gasPaidInOutputByRecipient"], 0)

    def test_real_exchange_illiquidity_is_rejected(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 1_000_000_000_000)
        self.assertEqual(result["candidate"]["status"], "revert")
        self.assertEqual(result["execution"]["status"], "not-attempted")

    def test_diagnostic_illiquidity_transaction_reverts_on_fork(self):
        result = run_fork_case(self.client, "cUSD", "USDT0", 1_000_000_000_000,
                               probe_illiquidity=True)
        self.assertEqual(result["candidate"]["status"], "revert")
        self.assertTrue(result["plan"]["diagnosticOnly"])
        self.assertEqual(result["plan"]["minimumOutput"], 0)
        self.assertEqual(result["execution"]["status"], "revert")
        self.assertEqual(result["execution"]["receiptStatus"], 0)
        self.assertEqual(result["execution"]["recipientDelta"], 0)
        self.assertGreater(result["execution"]["gasUsed"], 0)

    def test_dispatch_candidate_is_retained_after_real_router_validation(self):
        request = RouteRequest("verified-tempo", resolve_route("cUSD", "USDT0"), 25_000_000)
        batch = dispatch_quotes(
            self.client, [request], HISTORICAL_CONTEXT,
            validator=lambda req, quote, block: validate_tempo_on_fork(self.client, req, quote, block),
        )
        self.assertEqual(batch["outcomes"][0]["quotePath"], "tempo_hook")
        self.assertEqual(batch["outcomes"][0]["validationStatus"], "validated")
        self.assertEqual(batch["comparisonInput"][0]["amountOut"], 24_997_499)
        self.assertEqual(batch["comparisonInput"][0]["routeId"], "verified-tempo")
        self.assertEqual(batch["comparisonInput"][0]["gasPaidInOutputByRecipient"], 0)

    def test_single_hop_pathusd_gas_is_reconciled_and_compared(self):
        request = RouteRequest("path-usd", resolve_route("cUSD", "PathUSD"), 1_000_000)
        batch = dispatch_quotes(
            self.client, [request], HISTORICAL_CONTEXT,
            validator=lambda req, quote, block: validate_tempo_on_fork(self.client, req, quote, block),
        )
        outcome = batch["outcomes"][0]
        self.assertEqual(outcome["quoteStatus"], "candidate")
        self.assertEqual(outcome["validationStatus"], "validated")
        self.assertEqual(outcome["recipientDelta"], 999_479)
        self.assertEqual(outcome["gasPaidInOutputByRecipient"], 321)
        self.assertEqual(batch["comparisonInput"][0]["amountOut"], 999_800)
        self.assertEqual(batch["comparisonInput"][0]["recipientDelta"], 999_479)


if __name__ == "__main__":
    unittest.main()
