# Uniswap v4 EXACT_IN quote regression report

The follow-up using deployed Tempo pools and Universal Router is in [REAL_TEMPO_REPORT.md](REAL_TEMPO_REPORT.md). Investigation date: 2026-09-26. No production transaction was sent. `results.txt` records **13/13 passing tests**, including tests deliberately reproducing missing quotes.

## Source and fixture

| Repository | Checkout used | Commit |
|---|---|---|
| v4-core | `/Users/harry/uniswap-v4-study/v4-core` | `46c6834698c48bc4a463a86d8420f4eb1d7f3b75` |
| v4-periphery | `/Users/harry/uniswap-v4-study/v4-periphery` | `9969eec44cfdf07e24b41de47f40276a58401976` |
| v4-hooks-public | `/Users/harry/uniswap-v4-study/v4-hooks-public` | `e4eabe526f9b516fff78d98ba781251747f0fd6e` |
| uniroute-public | `/Users/harry/uniswap-v4-study/uniroute-public` | `2961efa8d44b80d353ee3af82cf868702bb6ab6a` |
| universal-router | `/Users/harry/uniswap-v4-study/universal-router` | `543e1a19d6e21e31ced2512eec5792b50f13a0ba` |

Foundry v1.8.3 and solc 0.8.26 (PoolManager) and 0.8.29 (harness/hook) were installed. The v4-hooks-public submodules were present. The imported `V4Quoter.sol` matched the checked v4-periphery file by `cmp`; `PoolManager.sol` and `IPoolManager.sol` matched the corresponding submodule copies.

- A, B, and C were six-decimal `MockTIP20` tokens. `alice` held 10^12 raw units of each and approved the router. No-hook and fee-hook pools had 10^9 liquidity over ticks +/-600, zero LP fee, and initial 1:1 price. The B/C pool deposited about 29.55 million raw B units into PoolManager. Standard input was 1,000,000 raw units (one token).
- `FixedOutputFeeHook` took 100 raw **output** units from PoolManager in `afterSwap` and required `hookData=0x42`. Fee-on/off runs began from the same snapshot. H1 and H2 were separate instances, and the hook's actual token receipts were checked.
- The real `TempoExchangeAggregator.sol` implementation was used; only the external precompile was replaced by `MockTempoExchange`. The mock charged 0.1% and held 10^12 A/B units. PoolManager was **not** seeded with A in G or H-first. In H-last it held A deposited by the C/A pool LP. The explicitly named `explicit_manager_seed_diagnostic` artificially minted 1,000,000 A into PoolManager before **both** quote and execution.
- Quotes used `V4Quoter.quoteExactInput`; G additionally used direct `hook.quote`. Each quote and `ExactInPathRouter.swapExactIn` execution began from the same caller and state. The diagnostic router opened **one** `PoolManager.unlock`, settled Alice's input before swapping, ran all hops within that transaction, then took final output. It is **not** UniRoute or Universal Router production calldata. Gas below measures its complete call.
- Alice was the EOA in both paths, but hooks received V4Quoter as `sender` during quoting and ExactInPathRouter during execution. The fixture hooks did not restrict `sender`; permissioned hooks require separate checks.

## Results

Outputs are raw smallest token units. `quote / execution` compares the **same route**. `revert` means no standard quote. Gas is the fee-on case when applicable.

| Case | Quote / execution | Diagnostic-router gas | Finding |
|---|---:|---:|---|
| A: A -> B, no hook | 999000 / 999000 | 111641 | PASS: one-hop control |
| B: A -> B -> C, no hook | 998002 / 998002 | 143961 | PASS: multi-hop control |
| C: A -> B via H1, fee off/on | 999000 / 999000; 998900 / 998900 | 191753 | PASS: H1 received 100 B when enabled |
| D: A -> B via H1 -> C, fee off/on | 998002 / 998002; 997903 / 997903 | 231374 | PASS: first-hop H1 was called and received 100 B |
| E: C -> A -> B via H1, fee off/on | 998002 / 998002; 997902 / 997902 | 229402 | PASS: last-hop H1 was called and received 100 B |
| F: A -> B via H1 -> C via H2, fees off/on | 998002 / 998002; 997803 / 997803 | 311488 | PASS: H1 received 100 B and H2 received 100 C |
| G: A -> B via Tempo hook | V4Quoter reverts; direct hook quote 999000 / 999000 | 230464 | Missing standard quote reproduced; direct quote matched execution |
| H-first: A -> B via Tempo hook -> C | V4Quoter reverts; composed candidate 998002 / 998002 | 252984 | Missing quote despite successful full diagnostic-router execution; composition was checked |
| H-last: C -> A -> B via Tempo hook | 998001 / 998001 | 258312 | PASS: standard quoter worked because the C/A LP had deposited 29,553,011 A in PoolManager |
| H-first with artificial PoolManager A funding | 998002 / 998002 | 235884 | PASS: balance diagnostic; `MockTIP20.mint` added 1,000,000 A before both paths |
| H-first, no PoolManager A funding; inputs 1,000 / 1m / 10m / 25m | V4Quoter reverts for all; execution 998 / 998002 / 9891187 / 24366447 | 252884 / 403784 / 416793 / 417192 | PASS: multiple amounts reproduced; 25m neared the B/C pool's B balance |
| Invalid hook data `0x` | Both revert `WrongHookData` | N/A | PASS: the hook enforced its data requirement |
| Genuine no-hook liquidity shortage, input 10^12 | Quote: `NotEnoughLiquidity`; execution: `PartialFill(30452989,10^12)` | N/A | PASS: valid rejection, not a missed executable trade |

## Traces and interpretation

`trace_F.txt` shows both H1 and H2 `afterSwap(...,0x42)` callbacks **inside V4Quoter**, followed by the intentional `QuoteSwap(997803)` revert. Router execution invokes both callbacks again and transfers the fees. This fixture rejects the hypothesis that standard v4 multi-hop inherently skips custom-hook rules.

`trace_H_first.txt` shows `V4Quoter.quoteExactInput -> PoolManager.swap -> TempoExchangeAggregator.beforeSwap -> PoolManager.take(A, hook, 1,000,000) -> token A transfer revert`, because PoolManager held zero A. That is a **real failure**, not the intentional `QuoteSwap` return. From the same snapshot, the diagnostic router settled A first; the hook ran, the mock exchange returned 999,000 B for 1,000,000 A, and the B/C pool produced 998,002 C. `trace_H_last.txt` confirms the last-hop hook ran and the quoter worked because the C/A LP deposited A. `trace_illiquid.txt` distinguishes genuine liquidity failure; `trace_wrong_data.txt` records `WrongHookData` in both paths.

In the checked UniRoute source, `AggHookQuoter.ts:31-35` selects only **single-hop** `isTempoAggHook` routes for direct hook quotes; `DeepQuoteStrategy.ts:156-252` sends multi-hop routes to the standard fetcher. H-first has the relevant mechanism **if** the hook is recognized and the pool enters routing. The public checkout lacks `package.json`, `src/lib/helpers.ts` (the missing `isTempoAggHook` implementation), `src/lib/methodParameters.ts`, and `src/models`. The full service, production hook set, and actual candidate selection could not be tested. This fixture does not prove that a correctly quoted route was later excluded from comparison.

## Reproduction and other evidence

The archived Foundry harness requires the original `uniswap-v4-study` source checkouts and library layout:

```bash
cd /Users/harry/uniswap-v4-study/quote-harness
FORGE_BIN=/Users/harry/.foundry/bin/forge ./run.sh
/Users/harry/.foundry/bin/forge test --offline --match-test test_H_tempo_first_quoter_fails_but_router_succeeds -vvvv
```

Before tracing, `v4-core/out/PoolManager.sol/PoolManager.json` must exist; `run.sh` builds it. The archived `results.txt` and `trace_*.txt` files sit beside this report. Additional Tempo chain 4217 checks are in `../tempo_rpc_probe.py`, `../tempo_probe_41274562.jsonl`, and `../tempo_replay_4.jsonl`. At block 41,274,562, four historical single-hop EXACT_IN transactions through hook `0x7169a78a59f136876e724b648fbb339a42f46888` were replayed via `eth_call` with their original caller/calldata; all four succeeded and matched direct hook quotes. Those observations do not measure production multi-hop behavior or real-world failure frequency.
