"""Check the dashboard's one-run record and admission conditions."""

import unittest
from unittest.mock import patch

from dashboard_proof import build_record
from tempo_quote import (HISTORICAL_CONTEXT, MANAGER, PAYER, TOKENS, RpcError,
                         run_fork_case)


def fork_result(amount=25_000_000, quoted=24_997_499):
    return {
        "chainId": HISTORICAL_CONTEXT.chain_id,
        "parentBlock": HISTORICAL_CONTEXT.number,
        "blockHash": HISTORICAL_CONTEXT.hash,
        "route": "cUSD -> PathUSD -> USDT0",
        "amountIn": amount,
        "poolManagerInputBalance": 19_862_459,
        "payerInputBalanceBeforeFunding": 5_249_475,
        "testFunding": [{"account": PAYER, "token": "cUSD", "balanceSetTo": amount}],
        "standardQuote": {"status": "revert", "error": "execution reverted"},
        "candidate": {"status": "candidate", "amountOut": quoted,
                      "hops": [{"source": "cUSD", "target": "PathUSD",
                                "amountIn": amount, "amountOut": amount - 5_000},
                               {"source": "PathUSD", "target": "USDT0",
                                "amountIn": amount - 5_000, "amountOut": quoted}]},
        "plan": {"to": "0xrouter", "from": PAYER, "data": "0x1234", "value": "0x0",
                 "payer": PAYER, "recipient": PAYER, "deadline": 1_790_346_234,
                 "minimumOutput": quoted - 100_000,
                 "actions": ["SETTLE", "SWAP_EXACT_IN", "TAKE"]},
        "execution": {"status": "success", "recipientDelta": quoted,
                      "grossOutputTransfer": quoted, "gasUsed": 316_216,
                      "hookCalls": 2, "localForkTxHash": "0x" + "12" * 32,
                      "feeToken": TOKENS["cUSD"], "feePayer": PAYER,
                      "outputTokenTransfers": [{"from": MANAGER, "to": PAYER,
                                                "amount": quoted}]},
        "metrics": {"rpcCalls": 23, "elapsedMs": 1_478.6},
    }


class DashboardProofTests(unittest.TestCase):
    def test_gap_requires_a_live_quote_and_matching_recipient_delta(self):
        record = build_record("gap", fork_result())
        self.assertEqual(record["baseline"]["errorStage"], "PoolManager.take(cUSD)")
        self.assertEqual(record["comparison"]["status"], "matched")
        self.assertEqual(record["comparison"]["deltaRaw"], 0)
        self.assertTrue(record["whyThisMatters"])
        self.assertEqual(record["plan"]["actions"], ["SETTLE", "SWAP_EXACT_IN", "TAKE"])

    def test_small_control_does_not_claim_a_recovered_gap(self):
        result = fork_result(amount=1_000_000, quoted=999_899)
        result["standardQuote"] = {"status": "success", "amountOut": 999_899}
        record = build_record("small", result)
        self.assertEqual(record["comparison"]["status"], "matched")
        self.assertFalse(record["whyThisMatters"])

    def test_illiquidity_probe_is_never_admitted_as_a_quote(self):
        result = fork_result(amount=1_000_000_000_000)
        result["candidate"] = {"status": "revert",
                               "error": "execution reverted: custom error 0xbb55fd27"}
        result["plan"]["minimumOutput"] = 0
        result["plan"]["diagnosticOnly"] = True
        result["execution"] = {"status": "revert", "phase": "Tempo Exchange: InsufficientLiquidity()",
                               "error": "custom error 0xbb55fd27", "receiptStatus": 0,
                               "recipientDelta": 0, "gasUsed": 250_000}
        record = build_record("illiquid", result)
        self.assertEqual(record["quoteBridge"]["error"], "InsufficientLiquidity()")
        self.assertEqual(record["plan"]["status"], "diagnostic")
        self.assertEqual(record["execution"]["receiptStatus"], 0)
        self.assertEqual(record["comparison"]["status"], "not-comparable")
        self.assertFalse(record["whyThisMatters"])

    def test_liquidity_probe_sends_full_router_call_then_reverts_snapshot(self):
        class ProbeClient:
            url = "http://127.0.0.1:8549"

            def __init__(self):
                self.count = 0
                self.calls = []

            def pinned_block(self, context):
                return {"timestamp": hex(1_790_342_634)}

            def balance(self, token, account):
                return 19_862_459 if account == MANAGER else 1_000_000_000_000 if token == TOKENS["cUSD"] else 0

            def rpc(self, method, params):
                self.calls.append(method)
                self.count += 1
                if method == "eth_call":
                    raise RpcError("custom error 0xbb55fd27")
                return {"eth_blockNumber": hex(HISTORICAL_CONTEXT.number),
                        "evm_snapshot": "0x1", "eth_getBalance": hex(10**18),
                        "anvil_impersonateAccount": True,
                        "eth_sendTransaction": "0x" + "12" * 32,
                        "eth_getTransactionReceipt": {"status": "0x0", "gasUsed": hex(250_000)},
                        "anvil_stopImpersonatingAccount": True,
                        "evm_revert": True}[method]

        client = ProbeClient()
        with (patch("tempo_quote.standard_quote", return_value={"status": "revert", "error": "transfer"}),
              patch("tempo_quote.quote_candidate", side_effect=RpcError("custom error 0xbb55fd27")),
              patch("tempo_quote._cast", return_value="0x1234")):
            result = run_fork_case(client, "cUSD", "USDT0", 1_000_000_000_000,
                                   probe_illiquidity=True)
        self.assertEqual(result["plan"]["actions"], ["SETTLE", "SWAP_EXACT_IN", "TAKE"])
        self.assertEqual(result["plan"]["minimumOutput"], 0)
        self.assertEqual(result["execution"]["receiptStatus"], 0)
        self.assertEqual(result["execution"]["recipientDelta"], 0)
        self.assertLess(client.calls.index("evm_snapshot"), client.calls.index("eth_sendTransaction"))
        self.assertLess(client.calls.index("eth_sendTransaction"), client.calls.index("evm_revert"))

    def test_input_and_output_mismatch_cannot_claim_success(self):
        with self.assertRaises(ValueError):
            build_record("small", fork_result())
        result = fork_result()
        result["execution"]["recipientDelta"] -= 1
        record = build_record("gap", result)
        self.assertEqual(record["comparison"]["status"], "mismatch")
        self.assertFalse(record["whyThisMatters"])

    def test_failed_snapshot_restore_invalidates_the_run(self):
        class FailedRestoreClient:
            url = "http://127.0.0.1:8549"

            def __init__(self):
                self.calls = []
                self.count = 0

            def pinned_block(self, context):
                return {"timestamp": hex(1_790_342_634)}

            def rpc(self, method, params):
                self.calls.append(method)
                return {"eth_blockNumber": hex(HISTORICAL_CONTEXT.number),
                        "evm_snapshot": "0x1", "evm_revert": False}[method]

            def balance(self, token, account):
                raise ValueError("simulated read failure after snapshot")

        client = FailedRestoreClient()
        with self.assertRaisesRegex(RpcError, "snapshot could not be restored"):
            run_fork_case(client, "cUSD", "USDT0", 25_000_000)
        self.assertEqual(client.calls, ["eth_blockNumber", "evm_snapshot", "evm_revert"])


if __name__ == "__main__":
    unittest.main()
