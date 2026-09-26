# Verified Tempo multi-hop quote prototype

This standalone Python adapter restores a **candidate exact-input quote** for three pinned Tempo v1.0 route shapes and encodes a complete Universal Router V4 command. It then checks the command with `eth_call` and `debug_traceCall`, executes it **only on a snapshotted local Anvil fork**, reads the recipient's actual token-balance change and transaction receipt, and reverts the snapshot. It never broadcasts to Tempo mainnet. The existing UniRoute public checkout is incomplete, so this is an integration-ready boundary, **not** a claim that UniRoute production has been changed.

## Newly measured result

Fork parent: Tempo chain 4217, block **41,183,156**, hash `0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3`. Token units below are raw six-decimal units. The local test wallet's cUSD balance was set to 30,000,000 and its native gas balance to 1 ETH; PoolManager and Tempo Exchange balances were not changed. A fresh snapshot is used for each case.

| Route and input | Standard V4Quoter | New candidate | Full Universal Router transaction | Evidence |
|---|---:|---:|---:|---|
| cUSD -> PathUSD -> USDT0, 25,000,000 | Revert after first hook at `PoolManager.take` | 24,997,499 | Receipt status 1; recipient USDT0 **+24,997,499**; 2 hook calls; **316,216 receipt gas** | [`demo-results/tempo_25_cusd.json`](demo-results/tempo_25_cusd.json), fork regression |
| cUSD -> PathUSD -> USDT0, 1,000,000 | 999,899 | 999,899 | Recipient USDT0 +999,899 | fork regression |
| cUSD -> PathUSD -> USDC.e, 1,000,000 | 999,800 | 999,800 | Recipient USDC.e +999,800 | fork regression |
| cUSD -> PathUSD, 1,000,000 | 999,800 | 999,800 | Gross output transfer 999,800; recipient balance **+999,479**; 200,209 receipt gas | [`demo-results/tempo_singlehop_1_cusd.json`](demo-results/tempo_singlehop_1_cusd.json) |
| cUSD -> PathUSD -> USDT0, 1,000,000,000,000 | Revert | Direct hook quote reverts `InsufficientLiquidity()` | Not attempted: no valid quote | fork regression and [baseline trace](evidence/quote-harness/tempo_fork_trace_illiquid_clean.json) |

The 25 cUSD quote was **directly measured** to fail; it is not an extrapolation from the 19,862,459 cUSD PoolManager balance threshold. The new two-hop candidate quotes each hook at the same pinned block and feeds hop one output to hop two. The receipt and recipient balance delta confirm the complete prepay Router transaction. Gross and net are deliberately separated: in the one-hop PathUSD case, the output transfer matches the quote but the payer's net PathUSD balance rises by 321 fewer units. The current evidence does not isolate that 321-unit difference into a specific fee component. `debug_traceCall.gasUsed` and receipt `gasUsed` differ for these local transactions; use receipt gas for execution cost and do not conflate the two measurements.

The recorded 25 cUSD run used **5 RPC calls and 343.8 ms** for candidate quoting, and **23 RPC calls and 1,478.6 ms** for the whole quote/simulation/local-transaction cycle. These are one observed run on a warm local fork, not latency estimates for production. No validated competing route or justified gas-to-output conversion is available, so no after-gas price advantage or production loss is claimed.

## Run

Requires Python 3.12+ and Foundry `cast`/`anvil` (available in `PATH` or `~/.foundry/bin/cast` for encoding). The new module has no Python package dependencies. The archived investigation scripts in `evidence/` use `requests` separately. Start a **fresh** Anvil fork in terminal 1:

```bash
anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8547 --silent
```

In terminal 2, from this repository:

```bash
TEMPO_FORK_RPC=http://127.0.0.1:8547 python3 -m unittest discover -s tests -v
python3 tempo_demo.py --rpc http://127.0.0.1:8547 --source cUSD --target USDT0 --amount 25 --output demo-results/tempo_25_cusd.json
```

The demo prints route, amount, block, existing quoter status, candidate, execution status, output, gas, match and RPC/latency metrics. `--output` also saves the **complete** Universal Router calldata. The deadline in that calldata is tied to this historical fork block; it is **not** current-chain executable calldata. The plan uses 50 bps minimum-output protection, an explicit deadline, payer-as-user settlement, and a specified recipient. It assumes the payer already has sufficient Permit2 allowance; the historical payer did on this fork, as the full transaction demonstrates. No private key or Permit2 signature is generated.

## Scope and integration boundary

`tempo_quote.py` accepts only cUSD -> PathUSD, cUSD -> PathUSD -> USDT0, and cUSD -> PathUSD -> USDC.e at the verified block and deployed hook `0x7169a78a59f136876e724b648fbb339a42f46888`. Pool IDs, direction, fee 500, tick spacing 10, token addresses and six-decimal units are explicit. Other hooks, chains, blocks, reverse directions, arbitrary route composition, exact-output and untested source tokens are rejected. Independent hop quotes are marked **candidate** until the complete Router execution is checked; shared mutable exchange liquidity could invalidate a composed number at other amounts.

The API boundary is `resolve_route` -> `quote_candidate` -> `build_plan` -> `run_fork_case`. UniRoute could connect route classification and candidate insertion to the first two, and its existing `SwapStepsFactory` exact-input `SETTLE -> SWAP -> TAKE` path to the execution plan. That connection is **not present** here. The public UniRoute checkout at `2961efa8d44b80d353ee3af82cf868702bb6ab6a` lacks `src/lib/helpers.ts` (including `isTempoAggHook`), `src/lib/methodParameters.ts`, and `src/models`; the full service and active production route selection cannot be run. Current-block support, live Permit2 handling, route ranking, and state-interaction checks remain future integration work.

The original 13-test local investigation and real-contract baseline are preserved under [`evidence/`](evidence/README.md). They distinguish mocks, historical receipts, read-only RPC calls, and fork simulations. No unrelated Uniswap production logic was modified.
