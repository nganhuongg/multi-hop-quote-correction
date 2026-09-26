# Tempo: real-contract use cases for the multi-hop quote balance threshold

Investigation date: 2026-09-26; Tempo chain **4217**. No transaction was broadcast to Tempo, production code was not changed, and the 13 tests in `REPORT.md` were not rerun. Unless identified as a historical receipt, "execution" below means `eth_call`/`debug_traceCall` against the **deployed Universal Router**. Fork-only state changes are disclosed separately. This is an archived baseline report; [the new contribution](../../README.md) later measured full local-fork receipts and recipient balance changes.

| Use case | Quote path | Universal Router result | Validated alternative | After-gas advantage | Evidence |
|---|---:|---:|---|---|---|
| One-hop control: 5.249475 cUSD -> PathUSD, parent block 41,183,156 | `hook.quote`: 5.248425 PathUSD | 5.248425; historical receipt gas 206,811 | None | Not measured | Historical status-1 transaction and parent-block `eth_call` replay |
| 1 cUSD -> PathUSD -> USDT0, block 41,183,156 | 0.999899 USDT0 | 0.999899; trace gas 323,356 | None verified | Not measured | Real RPC, same block/caller, two hook calls |
| 1 cUSD -> PathUSD -> USDC.e, block 41,183,156 | 0.999800 USDC.e | 0.999800; trace gas 312,156 | None verified | Not measured | Real RPC, same block/caller, two hook calls |
| 1 USDC.e -> PathUSD -> USDT0, block 41,115,563 | 1.000000 USDT0 | 1.000000; trace gas 585,524 | None verified | Not measured | Real RPC, historical Permit2 signature reused, two hooks |
| 1 USDC.e -> PathUSD -> cUSD, block 41,115,563 | 0.999800 cUSD | 0.999800; trace gas 578,524 | None verified | Not measured | Real RPC, historical Permit2 signature reused, two hooks |
| **U1/U3:** 19.862460 cUSD -> PathUSD -> USDT0, block 41,183,156 | **V4Quoter reverts** at `PoolManager.take(cUSD)` | **19.860473 USDT0**, trace gas **571,946**, with `SETTLE` before `SWAP`; swap-before-settle reverts | None verified | Not measured | Fork funded **only the payer's cUSD**; PoolManager and DEX unchanged |
| Genuine liquidity shortage: 1,000,000 cUSD input | Direct hook quote: `InsufficientLiquidity()` | Settle-before-swap also reverts | None | N/A | Fork funded payer; DEX not funded |

All listed tokens had **six decimals** according to `decimals()` at block 41,274,562. Token amounts are **not** automatically USD values. Except for the historical one-hop receipt, gas in this baseline table is `debug_traceCall.gasUsed` for the complete Universal Router call, not V4Quoter's gas estimate or a transaction receipt. `tempo_real_route_summary.json`, `tempo_fork_usecases_41183156.jsonl`, and `tempo_fork_trace_25m.json` hold the balances and traced output transfer. The historical one-hop receipt is in `tempo_onehop_control_41183156.json` and `../tempo_replay_4.jsonl`.

## Pools, addresses, and inventory limits

- PoolManager: `0x33620f62c5b9b2086dd6b62f4a297a9f30347029`; V4Quoter: `0x20e6487c371a2086f841ef453f85378223df4f4e`; Universal Router: `0x182a927119D56008d921126764bF884221b10f59`. Source: [Uniswap v4 deployments](https://developers.uniswap.org/docs/protocols/v4/deployments).
- Checked hook: **TempoExchangeAggregator v1.0** at `0x7169a78a59f136876e724b648fbb339a42f46888`. `aggregatorHookVersion()`, `tempoExchange()`, and `AggregatorPoolRegistered` were checked in `../tempo_probe_41274562.jsonl`. These results do **not** cover other hook deployments.
- PoolManager `Initialize` events in `tempo_pool_inventory_121m_123m.jsonl`: PathUSD `0x20c0000000000000000000000000000000000000` / USDC.e `0x20c000000000000000000000b9537d11c60e8b50`, pool ID `0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588`, block 12,180,656; PathUSD / cUSD `0x20c0000000000000000000000520792dcccccccc`, pool ID `0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57`, block 12,180,694; PathUSD / USDT0 `0x20c00000000000000000000014f22ca97301eb73`, pool ID `0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22`, block 12,180,723. All three use fee 500, tick spacing 10, and the checked hook.
- The four two-hop routes sampled four of the six permutations of non-PathUSD tokens through two aggregator pools. **Both hops use the Tempo hook.** They do not validate a liquid mixed Tempo/ordinary-v4 route. An ordinary PathUSD/USDC.e pool `0xce0d1c0b87a8b1a92cd0865013c2bd9440be49fdf7a3d3514e82f02352a4e2dd` was initialized at block 40,113,345, but V4Quoter reverted for a one-token sample at block 41,274,562; it is not a validated executable alternative. PathUSD/cbBTC pool `0x51d5133ef1f7317b98228f02f49a5a828035f2c2081584c553db622faa4c6830` also did not quote a one-token sample.
- Log searches were bounded: PathUSD blocks 12.1-12.3 million and 38-41.274562 million; cUSD blocks 12-15 million and 30-41.274562 million. `tempo_pool_inventory_*.jsonl` records provenance. No direct cUSD/USDT0 pool was found **in those ranges**; that does not rule out other ranges or protocols.

## Measured mechanism and limits

1. At block **41,183,156**, PoolManager held **19,862,459 raw cUSD**. Direct hook quotes still composed 25,000,000 cUSD -> 24,995,000 PathUSD -> 24,997,499 USDT0. V4Quoter succeeded at **19,862,459** input and reverted at **19,862,460**, one raw unit higher. `tempo_fork_trace_25m.json` shows the first hook called before `PoolManager.take(cUSD)` caused a TIP-20 transfer failure. This was a real failure, **not** the quoter's intentional `QuoteSwap` revert. On the fork, `anvil_dealTIP20` raised **only the payer** from 5,249,475 to 30,000,000 raw cUSD; PoolManager remained at 19,862,459 and the DEX was unchanged. Universal Router with `SETTLE(cUSD, amount, true) -> SWAP_EXACT_IN -> TAKE` executed and transferred **24.997499 USDT0** for 25 cUSD. Baseline trace gas was **571,946**. This shows a missing quote for a route executable **with prepayment**, not that UniRoute production already emits such calldata.
2. The trigger was settlement order, **not skipped hooks**. On the same fork, `SWAP -> SETTLE -> TAKE` failed at 19,862,460, 20,000,000, and 25,000,000 cUSD because the hook called `take` before payer tokens reached PoolManager. Below the threshold both orders succeeded and outputs matched (1 cUSD: 0.999899 USDT0; 19.862459 cUSD: 19.860472 USDT0). The real-RPC two-hop controls called **both hooks**. The 25-cUSD trace contains one hook call before quote/standard-order failure and two in successful prepay execution. The public UniRoute checkout lacks `methodParameters` and `isTempoAggHook` implementations, so actual production route inclusion and calldata mode remain unknown.
3. **No after-gas price improvement was measured.** The ordinary PathUSD/USDC.e pool lacked a validated execution at the comparison amount, and a direct cUSD/USDT0 route was not established. Real user frequency and production losses are unknown. Failure rates from deliberately chosen amounts near the threshold do not estimate user traffic. If an application issues only swap-before-settle calldata, restoring a quote alone would not make this above-threshold route executable.

Valid rejection control: at block 41,183,156, direct `hook.quote` for **1,000,000 cUSD** returned `InsufficientLiquidity()` (selector `0xbb55fd27`), and prepay execution also reverted inside Tempo Exchange despite sufficient test-wallet input (`tempo_fork_trace_illiquid.json`). This separates external DEX illiquidity from the PoolManager balance threshold.

## Evidence and reproduction

- **Real RPC, no overrides:** four two-hop route shapes, matching block/caller/allowance, output inferred from Universal Router call traces with both hooks. Historical wallets were taken from transactions `0x8745491a51213e9728db9b6597642cdbd26581f0d85392354e23140cc6f3dae1` and `0xf7a35c2895756f201ab93bfe7dda27345b88f684172f3bb670b47c8d4084bf4a`. The USDC.e route reused its original Permit2 signature at the parent block. These synthetic two-hop calls are not historical two-hop receipts.
- **Fork with payer override:** threshold and genuine-illiquidity controls. The fork used deployed hook, PoolManager, DEX, and Universal Router code. `tempo_fork_usecases.py` snapshots and reverts, changing only the payer's TIP-20 balance. Do not treat it as an unmodified historical replay.
- **Code:** UniRoute public `AggHookQuoter.ts:31-35` directly quotes only one-hop hook routes; `DeepQuoteStrategy.ts:156-252` sends multi-hop to the standard quoter. V4Quoter simulates swaps in `PoolManager.unlock`; Tempo's hook calls `PoolManager.take` in `beforeSwap`. Universal Router supports settlement before swap, while inspected historical calldata used swap before settlement. UniRoute's active production mode is unverified.
- Checked commits: v4-core `46c6834698c48bc4a463a86d8420f4eb1d7f3b75`; v4-periphery `9969eec44cfdf07e24b41de47f40276a58401976`; v4-hooks-public `e4eabe526f9b516fff78d98ba781251747f0fd6e`; uniroute-public `2961efa8d44b80d353ee3af82cf868702bb6ab6a`; universal-router `543e1a19d6e21e31ced2512eec5792b50f13a0ba`.

```bash
cd evidence/quote-harness
python3 tempo_multihop_replay.py --source cusd --target usdt0 --block 41183156 --amount 1000000 --amount 5249475 --trace
python3 tempo_multihop_replay.py --source usdce --target usdt0 --payer 0x915926b61b61ef91ea00a46cccf6a85c289b32a1 --block 41115563 --amount 1000000 --permit-template-tx 0xf7a35c2895756f201ab93bfe7dda27345b88f684172f3bb670b47c8d4084bf4a --trace
```

For the fork baseline, start Anvil in another terminal; the following script calls **only local RPC**:

```bash
anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8546 --silent
cd evidence/quote-harness
python3 tempo_fork_usecases.py --rpc http://127.0.0.1:8546 --trace-file /tmp/tempo_fork_trace_25m.json
```

Decision at the baseline stage: the **balance threshold and viable prepay execution** were established with deployed contracts, but a production price-quality loss was not. Production calldata mode, comparable executable alternatives, and after-gas output remain to be verified before making that claim.
