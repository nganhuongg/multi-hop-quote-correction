# Tempo-Uniswap v4 multi-hop quote gap: test evidence and contribution direction

**Investigation date:** 26 September 2026
**Scope:** EXACT_IN. No production transaction was sent. No product logic was changed.
**Decision:** The balance-dependent quote gap is sufficiently reproduced to justify a **prototype** that quotes and simulates the matching executable route. It is **not** yet evidence that the Uniswap app selected a worse trade, that users lost money, or that every Tempo hook is affected.

## 1. What was demonstrated

At Tempo block **41,183,156** (chain ID **4217**), the Uniswap v4 PoolManager held **19,862,459 raw cUSD units** (**19.862459 cUSD**). For the real two-hop route **cUSD -> PathUSD -> USDT0**, V4Quoter succeeded at that exact input and failed at **19,862,460 raw units**, one smallest unit higher. The first Tempo hook requested the input through `PoolManager.take`; the PoolManager's cUSD transfer reverted before V4Quoter could produce its intentional `QuoteSwap` result. [F1][T1][C3-C5]

On a fresh local fork of that block, setting **only the test payer's cUSD balance** from **5,249,475** to **30,000,000 raw units** allowed the deployed Universal Router to execute the same route when the V4 action order was **`SETTLE -> SWAP_EXACT_IN -> TAKE`**. At **25 cUSD** input it delivered **24.997499 USDT0**, exactly matching the two direct hook quotes, and used **571,946 gas** in `debug_traceCall`. With **`SWAP -> SETTLE -> TAKE`**, both V4Quoter and Universal Router failed above the PoolManager balance. Neither PoolManager nor Tempo Exchange was funded in the fork case. [F1][T1]

This is a **missing quote for a conditionally executable route**, not a demonstrated incorrect amount in a successful quote. The condition matters: an application using only swap-before-settle calldata would also fail to execute it. Public UniRoute source contains an EXACT_IN swap-steps builder that emits settle-before-swap, but its production activation and route inclusion were not verified. [C1-C6]

### Evidence labels

| Label | What it establishes | What it does not establish |
|---|---|---|
| [L1] | 13 local Foundry tests, including mock Tempo Exchange and a diagnostic full-route router | Tempo production behavior or Universal Router integration |
| [R1] | Read-only calls to real Tempo deployments at pinned historical blocks, real caller/allowance, and deployed Universal Router traces | That these synthetic multi-hop calldata were selected by production UniRoute |
| [F1] | Fresh Tempo fork, real deployed contracts, payer-only TIP-20 balance adjustment, paired quote and full Universal Router calls from the same state | A transaction that a real, unfunded historical payer could have sent at 25 cUSD |
| [C1-C6] | Behavior visible in the checked source files | Hidden configuration, missing modules, and production deployment behavior |
| [T1] | Saved call traces, raw errors, and output-token transfers | Frequency or economic impact in user traffic |

Token quantities below use decimal points. `cUSD`, `USDT0`, `USDC.e`, and `PathUSD` each returned **6 decimals** at block 41,274,562; their names alone are **not** treated as proof of a $1 price. Gas units are not converted to dollars or output tokens.

## 2. The full test inventory

### 2.1 Local regression fixture -- all 13/13 expected assertions passed [L1]

`PASS` includes tests whose **expected result is a revert**. A/B/C are fixture tokens with 6 decimals. The Tempo hook implementation is real source code, but its external Tempo Exchange is a mock; the router is a diagnostic single-transaction router, not Universal Router. Gas is for that diagnostic router.

| Test | Quote and full-route execution, raw output units | Router gas / error | Insight |
|---|---|---|---|
| A: A->B, no hook | 999,000 = 999,000 | 111,641 | One-hop control |
| B: A->B->C, no hook | 998,002 = 998,002 | 143,961 | Multi-hop alone is not the failure |
| C: A->B, fee hook off / on | 999,000 = 999,000 / 998,900 = 998,900 | 140,966 / 191,753 | Hook takes 100 output units when enabled |
| D: fee hook at first hop, off / on | 998,002 = 998,002 / 997,903 = 997,903 | 173,287 / 231,374 | First-hop custom rule is applied |
| E: fee hook at last hop, off / on | 998,002 = 998,002 / 997,902 = 997,902 | 178,615 / 229,402 | Last-hop custom rule is applied |
| F: two fee hooks, off / on | 998,002 = 998,002 / 997,803 = 997,803 | 202,613 / 311,488 | Both hooks are called and each receives 100 output units |
| G: A->B, Tempo hook | V4Quoter **reverts**; direct `hook.quote` 999,000 = execution 999,000 | 230,464 | Direct quote can avoid the PoolManager-balance dependency |
| H-first, explicit PM seed | 998,002 = 998,002 after **1,000,000 A minted to PM** | 235,884 | Artificial diagnostic; PM balance changes the outcome |
| H-first, no PM seed, inputs 1,000 / 1m / 10m / 25m | V4Quoter **reverts** for all; execution 998 / 998,002 / 9,891,187 / 24,366,447 | 252,884 / 403,784 / 416,793 / 417,192 | Diagnostic router pays before swapping; not proof of production routing |
| H-first, 1m A | V4Quoter **reverts**; two-leg candidate 998,002 = execution 998,002 | 252,984 | `take(A)` fails in the quote, while the paid-first full route succeeds |
| H-last, 1m input | 998,001 = 998,001; PM already holds **29,553,011 A** | 258,312 | Hook location alone does not predict failure |
| Fee hook with wrong `hookData` | Quote **reverts**; execution **reverts** | `WrongHookData` | A legitimate hook-condition failure |
| No-hook, genuinely insufficient liquidity, input 10^12 | Quote **reverts**; execution **reverts** | `NotEnoughLiquidity` / `PartialFill(30452989,10^12)` | Do not classify every failed quote as a missed trade |

The fee-hook off/on comparisons start from the same snapshot. The fixture does not merely compare two functions sharing a formula: traces show token fees actually transferred to the hooks. `trace_F.txt` shows both callbacks in V4Quoter and execution. `trace_H_first.txt` shows `PoolManager.take(A)` failing during quote; `trace_H_last.txt` shows a successful quote when PM already has the needed input. Sources: [REPORT.md](REPORT.md), [results.txt](results.txt), [test/QuoteRegression.t.sol](test/QuoteRegression.t.sol), and the named `trace_*.txt` files.

### 2.2 Real Tempo deployments and pool discovery [R1]

The tested hook is **TempoExchangeAggregator v1.0** at `0x7169a78a59f136876e724b648fbb339a42f46888`; its `tempoExchange()` points to `0xdec0000000000000000000000000000000000000`. This report does **not** generalize the result to other deployed Tempo aggregator hooks or arbitrary custom hooks. Pool IDs below came from PoolManager `Initialize` events and hook registration data, not invented token pairs.

| Component / pool | Address or pool ID | Discovery |
|---|---|---|
| PoolManager | `0x33620f62c5b9b2086dd6b62f4a297a9f30347029` | Tempo v4 deployment |
| V4Quoter | `0x20e6487c371a2086f841ef453f85378223df4f4e` | Tempo v4 deployment |
| Universal Router | `0x182a927119D56008d921126764bF884221b10f59` | Tempo deployment and historical transactions |
| PathUSD / USDC.e via tested hook | `0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588` | Initialize block 12,180,656; fee 500, spacing 10 |
| PathUSD / cUSD via tested hook | `0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57` | Initialize block 12,180,694; fee 500, spacing 10 |
| PathUSD / USDT0 via tested hook | `0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22` | Initialize block 12,180,723; fee 500, spacing 10 |

Token addresses: PathUSD `0x20c0000000000000000000000000000000000000`; cUSD `0x20c0000000000000000000000520792dcccccccc`; USDT0 `0x20c00000000000000000000014f22ca97301eb73`; USDC.e `0x20c000000000000000000000b9537d11c60e8b50`. The four tested two-hop routes use **two Tempo-hook v4 pools** each. They do not establish that a mixed route with one Tempo-hook pool and one ordinary v4 pool is liquid and executable. A no-hook PathUSD/USDC.e pool was found, but its one-token V4Quoter call reverted at block 41,274,562; it was not promoted to a validated alternative. Pool inventory and bounded search ranges are in [tempo_pool_inventory_121m_123m.jsonl](tempo_pool_inventory_121m_123m.jsonl), [tempo_pool_inventory_38m_411m.jsonl](tempo_pool_inventory_38m_411m.jsonl), and [REAL_TEMPO_REPORT.md](REAL_TEMPO_REPORT.md). The inventory was **not** a whole-chain scan.

### 2.3 Real-chain read-only replay: successful cases [R1]

All multi-hop rows below use the actual Universal Router deployment via `eth_call`/`debug_traceCall` at the **parent block of a historical payer transaction**, without state overrides. Each row's quote and execution use the same initial block, caller, and route. The trace contains **two calls to the tested hook** and a final output-token transfer to the payer. The USDC.e payer's original Permit2 permit command and signature were reused; omitting them would make this an invalid replay. These are synthetic **multi-hop calls**, not historical multi-hop transactions.

| Block | EXACT_IN route and amount | V4Quoter output | Router output | Difference | Full-call gas |
|---:|---|---:|---:|---:|---:|
| 41,183,156 | 1 cUSD -> PathUSD -> USDT0 | 0.999899 | 0.999899 | 0 | 323,356 |
| 41,183,156 | 5.249475 cUSD -> PathUSD -> USDT0 | 5.248949 | 5.248949 | 0 | 328,256 |
| 41,183,156 | 1 cUSD -> PathUSD -> USDC.e | 0.999800 | 0.999800 | 0 | 312,156 |
| 41,183,156 | 5.249475 cUSD -> PathUSD -> USDC.e | 5.248425 | 5.248425 | 0 | 317,056 |
| 41,115,563 | 1 USDC.e -> PathUSD -> USDT0 | 1.000000 | 1.000000 | 0 | 585,524 |
| 41,115,563 | 10.448955 USDC.e -> PathUSD -> USDT0 | 10.448954 | 10.448954 | 0 | 590,424 |
| 41,115,563 | 1 USDC.e -> PathUSD -> cUSD | 0.999800 | 0.999800 | 0 | 578,524 |
| 41,115,563 | 10.448955 USDC.e -> PathUSD -> cUSD | 10.446865 | 10.446865 | 0 | 583,424 |

At block 41,183,156, the payer held **5.249475 cUSD** and PM held **19.862459 cUSD**. At block 41,115,563, the USDC.e payer held **10.448955 USDC.e** and PM held **20,531.620657 USDC.e**. These balances explain why the unmodified quote simulation can get past the first hook for the tested amounts. [tempo_real_route_summary.json](tempo_real_route_summary.json) contains raw values, block, payer, pool IDs, trace hook counts, and gas for every row.

A separate **actual one-hop transaction** at parent block 41,183,156 exchanged **5.249475 cUSD for 5.248425 PathUSD**. Direct `hook.quote` returned **5.248425**, the receipt had status 1 and used **206,811 gas**, and replaying the original caller/calldata with `eth_call` succeeded. This is a one-hop control, not proof that all one-hop Tempo hook routes quote correctly. [tempo_onehop_control_41183156.json](tempo_onehop_control_41183156.json), [../tempo_replay_4.jsonl](../tempo_replay_4.jsonl).

### 2.4 Clean fork: the exact balance threshold and the two router orders [F1][T1]

Fresh fork at **41,183,156**. Before any override, payer cUSD = **5,249,475**, PM cUSD = **19,862,459** raw units. `anvil_dealTIP20` then set **payer cUSD = 30,000,000**. No PM or Tempo Exchange balance was changed. Each quote and each full-route call was an independent read-only simulation from this same adjusted state; the script restored its snapshot afterward. Direct-hook quote for the first leg and then the second leg is only a **candidate** until compared with full execution, as done below.

| Input cUSD | Direct hook 1 -> composed output USDT0 | V4Quoter | Router `SWAP->SETTLE` | Router `SETTLE->SWAP`, received USDT0 | Prepay gas |
|---:|---:|---:|---:|---:|---:|
| 1.000000 | 0.999800 -> 0.999899 | 0.999899 | success | 0.999899 | 571,922 |
| 19.000000 | 18.996200 -> 18.998099 | 18.998099 | success | 18.998099 | 571,946 |
| **19.862459** | 19.858486 -> 19.860472 | 19.860472 | success | 19.860472 | 571,946 |
| **19.862460** | 19.858487 -> 19.860473 | **revert** | **revert** | **19.860473** | 571,946 |
| 20.000000 | 19.996000 -> 19.997999 | **revert** | **revert** | **19.997999** | 571,922 |
| 25.000000 | 24.995000 -> 24.997499 | **revert** | **revert** | **24.997499** | 571,946 |

The threshold is **one raw unit above the PM balance**. At 25 cUSD the quoter's failure is a real transfer failure: trace path `V4Quoter -> PoolManager.swap -> TempoExchangeAggregator.beforeSwap -> PoolManager.take(cUSD) -> TIP-20.transfer(revert)`. It is **not** V4Quoter's intentional `QuoteSwap` revert, which is the mechanism it uses to return a successful quote. Swap-before-settle Universal Router fails at the same transfer. Prepay execution calls **both hooks**, then transfers **24,997,499 raw USDT0 units** to the payer. [tempo_fork_usecases_clean_41183156.jsonl](tempo_fork_usecases_clean_41183156.jsonl), [tempo_fork_trace_25m_clean.json](tempo_fork_trace_25m_clean.json), [QuoterRevert.sol](../v4-periphery/src/libraries/QuoterRevert.sol).

**Valid failure control:** with **1,000,000 cUSD** input (1,000,000,000,000 raw units), the payer alone was funded on the fork. Direct first-leg `hook.quote` returned `InsufficientLiquidity()` (`0xbb55fd27`), and prepay Universal Router execution reverted at the **Tempo Exchange** with the same selector. This is an external-liquidity failure, not the PM-balance quote gap. [tempo_fork_trace_illiquid_clean.json](tempo_fork_trace_illiquid_clean.json).

**Discarded harness errors:** Early replay attempts encoded `ExactInputParams` without its `minHopPriceX36` array, then encoded `SETTLE` with two words instead of `(currency, amount, payerIsUser)`. Those calls reverted before providing a valid route observation. A USDC.e replay initially omitted the historical Permit2 permit and failed at Permit2; the final replay includes the original signed command. None of these setup mistakes are counted as product defects or as rows of evidence above.

### 2.5 Supplementary probes, including cases outside this EXACT_IN decision

At block **41,274,562**, a read-only direct-hook probe sampled **80** combinations across **five registered pools, three hook addresses, two directions, four amounts, and EXACT_IN/EXACT_OUT**. For EXACT_IN, **38/40** direct hook calls succeeded and all 38 returned the same raw amount as the corresponding Tempo Exchange quote; the two failures were the cUSD pool at **10^12 raw units** in opposite directions. EXACT_OUT also had **38/40** successful direct hook calls, but only 8 of those raw hook values equaled the Exchange's raw quote. Buffering and execution were **not** analyzed for EXACT_OUT here, so the unequal values are not classified as errors. Four separate historical one-hop Universal Router transactions replayed successfully with original caller/calldata at their parent blocks; the cUSD example above is one of them. [../tempo_probe_41274562.jsonl](../tempo_probe_41274562.jsonl), [../tempo_replay_4.jsonl](../tempo_replay_4.jsonl).

A further **50 V4Quoter single-hop probes** at block 41,274,562 returned **28 values and 22 reverts** across three tested aggregator pools and two discovered ordinary v4 pools. The ordinary PathUSD/USDC.e and PathUSD/cbBTC pools each reverted in **10/10 deliberately sampled direction/amount calls**; no matching full execution was established for those pools, so they cannot serve as validated price alternatives. These are selected probes, **not** an estimate of failure frequency in user traffic. [tempo_real_probe_41274562.jsonl](tempo_real_probe_41274562.jsonl).

## 3. Mechanism in checked source

1. [AggHookQuoter.ts](../uniroute-public/src/core/strategy/AggHookQuoter.ts) accepts a Tempo aggregator hook route for direct `hook.quote` only if `route.path.length === 1`; its `ROUTE-1082` TODO explicitly names multi-hop. [DeepQuoteStrategy.ts](../uniroute-public/src/core/strategy/DeepQuoteStrategy.ts) partitions such routes and sends the rest to its standard quote fetcher. This is a **code-path conclusion**, not proof that a particular route entered production's candidate universe. The public checkout lacks `src/lib/helpers.ts` (the `isTempoAggHook` implementation), `src/lib/methodParameters.ts`, and `src/models`, so the full service and active recognition set could not be run from this snapshot. [C1-C2]
2. [V4Quoter.sol](../v4-periphery/src/lens/V4Quoter.sol) loops through every `PathKey`, calls `PoolManager.swap` with that hop's `hookData`, and intentionally reverts with a quote value only after swaps succeed. [BaseV4Quoter.sol](../v4-periphery/src/base/BaseV4Quoter.sol) bubbles a real swap failure. Multi-hop does **not** skip a custom hook. Ethers `callStatic` here is an off-chain simulated call; it does not imply that an EVM `STATICCALL` prevents the hook from executing inside the simulation. [C3]
3. [TempoExchangeAggregator.sol](../v4-hooks-public/src/aggregator-hooks/implementations/TempoExchange/TempoExchangeAggregator.sol) calls `poolManager.take(input, hook, amount)` **before** `tempoExchange.swapExactAmountIn` on EXACT_IN. [PoolManager.sol](../v4-core/src/PoolManager.sol) must transfer the requested input; a user's wallet balance does not automatically become a PoolManager balance. The hook and `take` are behaving as coded; the tested mismatch is between quote simulation and the viable pre-funded execution sequence. [C4-C5]
4. A useful integration path already exists in public code: [SwapStepsFactory.ts](../uniroute-public/src/core/swap/SwapStepsFactory.ts) builds EXACT_IN v4 actions as **`SETTLE(input, explicit amount) -> SWAP_EXACT_IN -> TAKE(output)`**, including a multi-hop `PathKey[]`; [SwapStepsFactory.test.ts](../uniroute-public/src/core/swap/SwapStepsFactory.test.ts) asserts that order. [SwapStepsBuilder.ts](../uniroute-public/src/core/swap/SwapStepsBuilder.ts) passes the steps to `SwapRouter.encodeSwaps`. But [UniRouteBL.ts](../uniroute-public/src/core/UniRouteBL.ts) gates this path on `universalRouterSwapsteps` and has a legacy fallback. Historical Tempo calldata inspected here used **`SWAP -> SETTLE -> TAKE`**. The public builder therefore makes reuse plausible; it does **not** establish which mode production requests use or whether its final calldata passes the 25-cUSD case. [C6][R1]

## 4. Problem statement and contribution direction

**User need:** A person has cUSD and wants the best executable amount of USDT0. The routing system needs comparable quotes and executable calldata for each eligible path.

**Observed gap:** A candidate two-hop Tempo route has externally available liquidity, yet the standard V4Quoter path stops at PM input transfer once requested input exceeds PM's pre-existing cUSD balance. The directly quoted legs and the full prepay Universal Router call agree at 25 cUSD. The quote failure could prevent that candidate from entering a quote-based comparison **if production discovers and recognizes the route and emits prepay calldata**. No successful quote with an incorrect amount was observed in these cases.

**Prototype contribution:** Restore an EXACT_IN quote for specifically recognized Tempo aggregator-hook multi-hop routes **together with** an executable settlement path. A defensible prototype should:

1. Confirm route eligibility by chain, exact hook deployment/version, pool key, direction, and `hookData`; do not assume every custom hook shares this behavior.
2. Obtain a candidate quote from appropriate per-hop sources at a pinned block, preserving rounding and fee behavior. Treat composition only as a candidate when hops can affect shared liquidity.
3. Build or reuse the public settle-before-swap EXACT_IN swap-steps path; simulate the **entire Universal Router transaction** with the intended payer, token balance, approval/Permit2 state, and min-out. Reject candidates that fail execution, including genuine Tempo Exchange `InsufficientLiquidity` cases.
4. Compare **executed output after gas** against other validated routes at the same state. Keep PM-balance quote failures, external-liquidity failures, allowance failures, and successful quotes as separate metrics.

**Prototype acceptance gate:** reproduce the 19.862459/19.862460 threshold; recover the 25-cUSD candidate with output **24.997499 USDT0** under matched execution; preserve the correct small-amount and insufficient-liquidity controls; prove the final UniRoute-produced calldata, rather than manually assembled calldata, executes. After that, find a same-block alternative route that also executes and measure output net of gas. A failed quote alone is **not** a measured better-price opportunity.

### What remains unknown

- Whether the tested hook address is in production `isTempoAggHook` recognition and whether these pools reach route comparison. Public helper/allowlist data are incomplete.
- Whether production enables `universalRouterSwapsteps` for these requests, uses the legacy builder, or falls back after an encoding error.
- A validated direct/alternative cUSD->USDT0 route at the same block; therefore **no after-gas advantage in tokens or percent** was measured.
- Production request frequency, user exposure, and realized loss. The deliberately chosen 1/19/threshold/20/25-cUSD amounts are **not** a user-traffic sample. The aggregate of benchmark differences is **not** money lost.
- A liquid mixed route with a Tempo hook at one hop and an ordinary v4 pool at the other. The four real two-hop routes tested here use the same Tempo hook deployment on **both** hops.

**Practical decision:** Proceed with a bounded prototype of quote recovery plus final-calldata simulation. Do not describe the current evidence as a proven production price-ranking defect. If the active production path always swaps before settling, the first contribution must include executable prepayment; a quote-only change would surface a route that still cannot execute.

## 5. Raw artifacts, code versions, and reproduction

| Artifact | Purpose |
|---|---|
| [results.txt](results.txt), [REPORT.md](REPORT.md), `trace_*.txt` | Local 13-test suite and detailed traces |
| [tempo_real_route_summary.json](tempo_real_route_summary.json), `tempo_multihop_*.jsonl` | Eight no-override multi-hop quote/execution observations and full traces |
| [tempo_onehop_control_41183156.json](tempo_onehop_control_41183156.json), [../tempo_replay_4.jsonl](../tempo_replay_4.jsonl) | Historical one-hop receipt and replay |
| [../tempo_probe_41274562.jsonl](../tempo_probe_41274562.jsonl), [tempo_real_probe_41274562.jsonl](tempo_real_probe_41274562.jsonl) | 80 direct-hook/Exchange quote probes and 50 V4Quoter single-hop probes |
| [tempo_fork_usecases_clean_41183156.jsonl](tempo_fork_usecases_clean_41183156.jsonl), [tempo_fork_trace_25m_clean.json](tempo_fork_trace_25m_clean.json), [tempo_fork_trace_illiquid_clean.json](tempo_fork_trace_illiquid_clean.json) | Fresh-fork threshold, PM transfer error, prepay success, and real DEX illiquidity |
| [tempo_pool_inventory_121m_123m.jsonl](tempo_pool_inventory_121m_123m.jsonl), [../tempo_probe_41274562.jsonl](../tempo_probe_41274562.jsonl) | Pool creation/registration, deployment, token, and direct hook quote observations |

Checked commits: `v4-core` **46c6834698c48bc4a463a86d8420f4eb1d7f3b75**; `v4-periphery` **9969eec44cfdf07e24b41de47f40276a58401976**; `v4-hooks-public` **e4eabe526f9b516fff78d98ba781251747f0fd6e**; `uniroute-public` **2961efa8d44b80d353ee3af82cf868702bb6ab6a**; `universal-router` **543e1a19d6e21e31ced2512eec5792b50f13a0ba**. Foundry/Anvil **v1.8.3**. No repositories were pushed.

Run the existing local tests only if a fresh verification is wanted; they were **not rerun** to prepare this document. The read-only real-chain and fresh-fork commands are:

```bash
cd /Users/harry/uniswap-v4-study/quote-harness
python3 tempo_multihop_replay.py --source cusd --target usdt0 --block 41183156 --amount 1000000 --amount 5249475 --trace
python3 tempo_multihop_replay.py --source usdce --target usdt0 --payer 0x915926b61b61ef91ea00a46cccf6a85c289b32a1 --block 41115563 --amount 1000000 --permit-template-tx 0xf7a35c2895756f201ab93bfe7dda27345b88f684172f3bb670b47c8d4084bf4a --trace
```

In another terminal start a **local** fork, then run the diagnostic script (the script snapshots and restores the fork):

```bash
/Users/harry/.foundry/bin/anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8547 --silent
python3 tempo_fork_usecases.py --rpc http://127.0.0.1:8547 --trace-file tempo_fork_trace_25m_clean.json > tempo_fork_usecases_clean_41183156.jsonl
```

No command above broadcasts a transaction to Tempo mainnet. The fork diagnostic uses `anvil_dealTIP20` on the **payer only** and labels that intervention in its output.
