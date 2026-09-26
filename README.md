# Verified Tempo multi-hop quote prototype

This standalone Python adapter restores a **candidate exact-input quote** for three pinned Tempo v1.0 route shapes and encodes a complete Universal Router V4 command. It then checks the command with `eth_call` and `debug_traceCall`, executes it **only on a snapshotted local Anvil fork**, reads the recipient's actual token-balance change and transaction receipt, and reverts the snapshot. It never broadcasts to Tempo mainnet. The existing UniRoute public checkout is incomplete, so this is an integration-ready boundary, **not** a claim that UniRoute production has been changed.

## Quote-dispatch milestone

`quote_dispatch.dispatch_quotes` accepts a list of routes for one trade. It
sends only the explicitly verified Tempo hook shapes to `quote_candidate`,
leaves ordinary no-hook routes with the normal quoter adapter, and rejects
unverified custom hooks. Each outcome records quote and validation status
separately; only complete Router-validated candidates whose **executed swap
transfer** matches the quote, whose recipient token flows reconcile, and whose
validation binds the route, amount, block and execution-plan digest enter
`comparisonInput`. The one-hop PathUSD control now qualifies: the receipt
proves a 999,800 gross transfer and a separate 321-raw-PathUSD gas payment by
the payer-recipient, explaining its 999,479 wallet-balance increase. The gas
amount comes from the actual receipt, not a fixed adjustment. If those flows
cannot be separated, validation is indeterminate. An ordinary-quoter failure
never triggers a Tempo retry.
The ordinary quoter and validator in the comparison unit test are **boundary
mocks**, so that test proves dispatch and candidate retention, not an economic
advantage over a real competing route.

On the real Tempo fork, 25,000,000 raw cUSD units on
`cUSD -> PathUSD -> USDT0` change from standard quote **revert** to specialized
candidate **24,997,499 raw USDT0 units**. The complete Universal Router
transaction receives exactly **24,997,499** and uses **316,216 receipt gas**;
the validated candidate reaches `comparisonInput`. The measured dispatch demo
made 35 local RPC calls; this includes a separate standard quote and a repeated
candidate quote during execution validation, so it is not a production latency
benchmark. See [`demo-results/dispatch_25_cusd.json`](demo-results/dispatch_25_cusd.json).

The [PathUSD dispatch result](demo-results/dispatch_pathusd_1_cusd.json)
records gross output, wallet delta and gas paid in the output token separately.
The public TypeScript quote-dispatch change is supplied as a reproducible
[`patch`](patches/README.md) against UniRoute commit
`2961efa8d44b80d353ee3af82cf868702bb6ab6a`. It passes an isolated
boundary test and applies cleanly; it is not an end-to-end runnable UniRoute
service. Without a real injected validator, the TypeScript patch leaves all
specialized hook candidates ineligible. The Python dispatcher is the runnable
execution-validation gate.

## Newly measured result

Fork parent: Tempo chain 4217, block **41,183,156**, hash `0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3`. Token units below are raw six-decimal units. The local test wallet's cUSD balance was set to 30,000,000 and its native gas balance to 1 ETH; PoolManager and Tempo Exchange balances were not changed. A fresh snapshot is used for each case.

| Route and input | Standard V4Quoter | New candidate | Full Universal Router transaction | Evidence |
|---|---:|---:|---:|---|
| cUSD -> PathUSD -> USDT0, 25,000,000 | Revert after first hook at `PoolManager.take` | 24,997,499 | Receipt status 1; recipient USDT0 **+24,997,499**; 2 hook calls; **316,216 receipt gas** | [`demo-results/tempo_25_cusd.json`](demo-results/tempo_25_cusd.json), fork regression |
| cUSD -> PathUSD -> USDT0, 1,000,000 | 999,899 | 999,899 | Recipient USDT0 +999,899 | fork regression |
| cUSD -> PathUSD -> USDC.e, 1,000,000 | 999,800 | 999,800 | Recipient USDC.e +999,800 | fork regression |
| cUSD -> PathUSD, 1,000,000 | 999,800 | 999,800 | Gross output transfer 999,800; recipient balance **+999,479**; 200,209 receipt gas | [`demo-results/tempo_singlehop_1_cusd.json`](demo-results/tempo_singlehop_1_cusd.json) |
| cUSD -> PathUSD -> USDT0, 1,000,000,000,000 | Revert | Direct hook quote reverts `InsufficientLiquidity()` | Not attempted: no valid quote | fork regression and [baseline trace](evidence/quote-harness/tempo_fork_trace_illiquid_clean.json) |

The 25 cUSD quote was **directly measured** to fail; it is not an extrapolation from the 19,862,459 cUSD PoolManager balance threshold. The new two-hop candidate quotes each hook at the same pinned block and feeds hop one output to hop two. The receipt and recipient balance delta confirm the complete prepay Router transaction. Gross and net are deliberately separated: the one-hop PathUSD transfer equals the quote, while the payer-recipient's balance rise is 321 units lower because the receipt charges **321 PathUSD for gas** to that same wallet. The fee transfer log and a separate-recipient control establish the cause; see the [admission report](ADMISSION_REPORT.md). `debug_traceCall.gasUsed` and receipt `gasUsed` differ for these local transactions; use receipt gas for execution cost and do not conflate the two measurements.

The recorded 25 cUSD run used **5 RPC calls and 343.8 ms** for candidate quoting, and **23 RPC calls and 1,478.6 ms** for the whole quote/simulation/local-transaction cycle. These are one observed run on a warm local fork, not latency estimates for production. No validated competing route or justified gas-to-output conversion is available, so no after-gas price advantage or production loss is claimed.

## Run

Requires Python 3.12+, Foundry `cast` and `anvil`, and access to a Tempo archive RPC for the pinned fork block. The isolated upstream patch test additionally requires Node.js, a `tsc` executable in `PATH`, and an explicitly specified `uniroute-public` checkout at the recorded commit. The active Python adapter uses the standard library; archived scripts in `evidence/` additionally use `requests`. Install from a fresh checkout without relying on sibling source directories:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Optional, only for archived evidence scripts:
.venv/bin/python -m pip install -e '.[evidence]'
```

Put Foundry's `anvil` and `cast` in `PATH`, or use `~/.foundry/bin/anvil` and `~/.foundry/bin/cast`. The local fork must expose `evm_snapshot`, `anvil_dealTIP20`, impersonation, and `debug_traceCall`; a generic public RPC cannot run the fork regression. Start a **fresh** Anvil fork in terminal 1:

```bash
anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8547 --silent
```

In terminal 2, from this repository:

```bash
TEMPO_FORK_RPC=http://127.0.0.1:8547 python3 -m unittest discover -s tests -v
python3 tempo_demo.py --rpc http://127.0.0.1:8547 --source cUSD --target USDT0 --amount 25 --output demo-results/tempo_25_cusd.json
python3 dispatch_demo.py --rpc http://127.0.0.1:8547 --target USDT0 --amount 25 --output demo-results/dispatch_25_cusd.json
UNIROUTE_PUBLIC_DIR=/absolute/path/to/uniroute-public node scripts/test_upstream_patch.cjs
```

The demo prints route, amount, block, existing quoter status, candidate, execution status, output, gas, match and RPC/latency metrics. `--output` also saves the **complete** Universal Router calldata. The deadline in that calldata is tied to this historical fork block; it is **not** current-chain executable calldata. The plan uses 50 bps minimum-output protection, an explicit deadline, payer-as-user settlement, and a specified recipient. It assumes the payer already has sufficient Permit2 allowance; the historical payer did on this fork, as the full transaction demonstrates. No private key or Permit2 signature is generated.

## Scope and integration boundary

`tempo_quote.py` accepts only cUSD -> PathUSD, cUSD -> PathUSD -> USDT0, and cUSD -> PathUSD -> USDC.e at the verified block and deployed hook `0x7169a78a59f136876e724b648fbb339a42f46888`. Pool IDs, direction, fee 500, tick spacing 10, token addresses and six-decimal units are explicit. Other hooks, chains, blocks, reverse directions, arbitrary route composition, exact-output and untested source tokens are rejected. Independent hop quotes are marked **candidate** until the complete Router execution is checked; shared mutable exchange liquidity could invalidate a composed number at other amounts.

The standalone API boundary is `dispatch_quotes` -> `quote_candidate` ->
`build_plan` -> `run_fork_route_case`. The patch connects route classification
and candidate insertion to public UniRoute's `AggHookQuoter` and
`DeepQuoteStrategy`; its existing `SwapStepsFactory` contains an exact-input
`SETTLE -> SWAP -> TAKE` branch. The public UniRoute checkout at
`2961efa8d44b80d353ee3af82cf868702bb6ab6a` lacks `package.json`,
`src/lib/helpers.ts` (including `isTempoAggHook`),
`src/lib/methodParameters.ts`, and `src/models`; the full service and active
production route selection cannot be run. The TypeScript patch defines, but
cannot wire, the private service's real plan and validator. Current-block
support, live Permit2 handling, production ranking, and state-interaction
checks remain future integration work.

The original 13-test local investigation and real-contract baseline are preserved under [`evidence/`](evidence/README.md). They distinguish mocks, historical receipts, read-only RPC calls, and fork simulations. No unrelated Uniswap production logic was modified.
