// Recorded from three independent Anvil runs; each run restored its fork snapshot.
window.quoteBridgeEvidence = {
  provenance: {
    label: "Recorded Anvil fork runs",
    recordedOnUtc: "2026-09-27",
    anvilVersion: "1.8.3",
    forkRpc: "https://rpc.tempo.xyz",
    chainId: 4217,
    blockNumber: 41183156,
    blockHash: "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3",
    route: "cUSD -> PathUSD -> USDT0",
    note: "V4Quoter, both Tempo hook quotes, and the funded Universal Router transaction were measured from the same pinned fork state for each case."
  },
  cases: {
    gap: {
      caseId: "gap", chainId: 4217, blockNumber: 41183156,
      blockHash: "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3",
      route: "cUSD -> PathUSD -> USDT0", amountInRaw: 25000000,
      poolManagerInputBalanceRaw: 19862459,
      payerInputBalanceBeforeFundingRaw: 5249475,
      testFunding: [{ token: "cUSD", balanceSetTo: 30000000 }, { nativeGasBalanceSetTo: 1000000000000000000 }],
      baseline: { status: "revert", amountOutRaw: null, errorStage: "PoolManager.take(cUSD)", error: "Contract call reverted" },
      quoteBridge: {
        status: "candidate", amountOutRaw: 24997499, errorStage: null, error: null,
        hops: [
          { source: "cUSD", target: "PathUSD", amountInRaw: 25000000, amountOutRaw: 24995000 },
          { source: "PathUSD", target: "USDT0", amountInRaw: 24995000, amountOutRaw: 24997499 }
        ]
      },
      plan: { status: "built", actions: ["SETTLE", "SWAP_EXACT_IN", "TAKE"], minimumOutputRaw: 24872511,
        planDigest: "f5d7fcf6d7b5d4139b29eae8626a48373dc06f2c2eb792d402acb59f8beef598" },
      execution: { status: "success", receiptStatus: 1, recipientDeltaRaw: 24997499,
        grossOutputRaw: 24997499, gasUsed: 316216, hookCalls: 2,
        localForkTxHash: "0x736f4e7bb9ce234fa5cdd06bd9e23b223ac85e9e15a727bd74c18d3463acf216",
        errorStage: null, error: null },
      comparison: { status: "matched", deltaRaw: 0, toleranceRaw: 0,
        reason: "Recipient balance change equals the recovered quote" },
      whyThisMatters: true, snapshotReverted: true, rpcCalls: 27, elapsedMs: 24185.7
    },
    small: {
      caseId: "small", chainId: 4217, blockNumber: 41183156,
      blockHash: "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3",
      route: "cUSD -> PathUSD -> USDT0", amountInRaw: 1000000,
      poolManagerInputBalanceRaw: 19862459,
      payerInputBalanceBeforeFundingRaw: 5249475,
      testFunding: [{ nativeGasBalanceSetTo: 1000000000000000000 }],
      baseline: { status: "success", amountOutRaw: 999899, errorStage: null, error: null },
      quoteBridge: {
        status: "candidate", amountOutRaw: 999899, errorStage: null, error: null,
        hops: [
          { source: "cUSD", target: "PathUSD", amountInRaw: 1000000, amountOutRaw: 999800 },
          { source: "PathUSD", target: "USDT0", amountInRaw: 999800, amountOutRaw: 999899 }
        ]
      },
      plan: { status: "built", actions: ["SETTLE", "SWAP_EXACT_IN", "TAKE"], minimumOutputRaw: 994899,
        planDigest: "a4489cc26373cd23504afc4c1f46181dbfe1fdcc0370cbd957f1658fc144e06c" },
      execution: { status: "success", receiptStatus: 1, recipientDeltaRaw: 999899,
        grossOutputRaw: 999899, gasUsed: 316180, hookCalls: 2,
        localForkTxHash: "0xb1a9e4a928e10c256e7e4231205228da212f4c48279efd1b1b05dd809a36e3ea",
        errorStage: null, error: null },
      comparison: { status: "matched", deltaRaw: 0, toleranceRaw: 0,
        reason: "Recipient balance change equals the recovered quote" },
      whyThisMatters: false, snapshotReverted: true, rpcCalls: 26, elapsedMs: 24669.0
    },
    illiquid: {
      caseId: "illiquid", chainId: 4217, blockNumber: 41183156,
      blockHash: "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3",
      route: "cUSD -> PathUSD -> USDT0", amountInRaw: 1000000000000,
      poolManagerInputBalanceRaw: 19862459,
      payerInputBalanceBeforeFundingRaw: 5249475,
      testFunding: [{ token: "cUSD", balanceSetTo: 1000000000000 }, { nativeGasBalanceSetTo: 1000000000000000000 }],
      baseline: { status: "revert", amountOutRaw: null, errorStage: "V4Quoter call", error: "Contract call reverted" },
      quoteBridge: { status: "revert", amountOutRaw: null, hops: [],
        errorStage: "Tempo Exchange liquidity", error: "InsufficientLiquidity()" },
      plan: { status: "diagnostic", actions: ["SETTLE", "SWAP_EXACT_IN", "TAKE"], minimumOutputRaw: 0,
        planDigest: "0620f7edcdc89bb8befaced2f8341aaf2d1647ef56830dc5e87d4dc010f11f66" },
      execution: { status: "revert", receiptStatus: 0, recipientDeltaRaw: 0,
        grossOutputRaw: null, gasUsed: 729270, hookCalls: null,
        localForkTxHash: "0x244735fb83f92db9103b5c317f2ec3f52ae4811718273b71ebf66db584370d37",
        errorStage: "Universal Router preflight", error: "Contract call reverted" },
      comparison: { status: "not-comparable", deltaRaw: null, toleranceRaw: 0,
        reason: "QuoteBridge could not produce a candidate" },
      whyThisMatters: false, snapshotReverted: true, rpcCalls: 21, elapsedMs: 18915.6
    }
  }
};
