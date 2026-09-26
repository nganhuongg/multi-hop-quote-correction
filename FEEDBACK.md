# Uniswap developer feedback: quoting Tempo aggregator routes

**Project:** [multi-hop-quote-correction](https://github.com/nganhuongg/multi-hop-quote-correction)

**Integration studied:** Uniswap v4 PoolManager, V4Quoter, Universal Router,
TempoExchangeAggregator, and public UniRoute quote dispatch

**Test scope:** Exact-input swaps on Tempo (chain 4217), pinned to block
41,183,156; local Anvil fork and boundary tests

## What we built

We built a small standalone quote adapter that recognizes three verified
Tempo-hook route shapes, calls the deployed hook's `quote()` for each hop at
one pinned block, and feeds each output amount into the next hop. It produces
Universal Router calldata with input settlement before the V4 swap. A candidate
enters the comparison input only after a complete local-fork Router transaction
confirms its executed output, recipient token flow, gas payment, route, amount,
block and execution plan. We also prepared a [patch against public UniRoute](patches/README.md)
that shows the quote-dispatch and validation boundary. The patch's TypeScript
test uses mocks; the full private UniRoute service is not integrated or tested.

The [runbook](DEMO_RUNBOOK.md), [fork test](tests/test_tempo_fork.py), and
[recorded result](demo-results/dispatch_25_cusd.json) reproduce the main case.
At the recorded block, PoolManager held **19,862,459 raw cUSD**. For an input
of **25,000,000 raw cUSD** on **cUSD → PathUSD → USDT0**, the standard
`V4Quoter` reverted when the hook tried to take input from PoolManager. The
specialized quote returned **24,997,499 raw USDT0**. The complete deployed
Universal Router transaction on the local fork settled input first, delivered
**24,997,499 raw USDT0** to the recipient, and used **316,216 receipt gas
units**. Only the test payer was funded; PoolManager and Tempo Exchange were
not topped up. Multi-hop did call the custom hook: the issue was settlement
state during quote simulation, not skipped hook logic.

## What worked well

- The v4 hook and PoolManager interfaces made the failure traceable to a
  specific operation: `V4Quoter.quoteExactInput → PoolManager.swap →
  TempoExchangeAggregator.beforeSwap → PoolManager.take`.
- `TempoExchangeAggregator` exposes a direct quote method, allowing us to use
  the hook's own pricing and protocol-fee behavior instead of copying its
  formula into the adapter.
- Universal Router already supports a V4 action sequence that settles input
  before swapping. The public UniRoute `SwapStepsFactory` also contains a
  `SETTLE → SWAP → TAKE` exact-input branch, so the contribution does not
  require changing or redeploying Router contracts.

## Friction and concrete requests

1. **Document quote simulation requirements for hooks that move real tokens.**
   `V4Quoter` intentionally reverts to return a successful quote, but a hook's
   `PoolManager.take` can trigger a *different* revert if the manager lacks
   input tokens during simulation. A guide with a call trace, the expected
   settlement state, and how to distinguish these two revert classes would
   prevent developers from treating every missing quote as insufficient pool
   liquidity. [Baseline trace and analysis](evidence/quote-harness/REAL_TEMPO_REPORT.md)
2. **Show a supported quote-to-execution pattern for multi-hop aggregator
   hooks.** The public UniRoute source explicitly notes this gap as
   `ROUTE-1082`: its direct hook-quote path selects single-hop routes, while
   other routes enter the standard quote fetcher. An example should show
   per-hop block-pinned quotes, the limits of independent-hop composition,
   full-plan validation, and rejection of unsupported route shapes. Simply
   removing the single-hop guard would not compose the remaining hops.
   [Proposed boundary patch](patches/README.md)
3. **Make final-calldata validation easier to integrate.** A quote alone did
   not prove the route could execute. A useful public integration example
   would bind the quoted route, raw input, block, payer, recipient, Permit2
   assumptions, deadline, minimum output and final Universal Router calldata
   to one full-transaction simulation. It should keep a *candidate quote*
   separate from an *execution-validated quote* and preserve the failure
   reason when validation is unavailable.
4. **Clarify gas-token accounting on Tempo.** In a one-hop control, the swap
   transferred **999,800 raw PathUSD**, while the payer-recipient wallet rose
   **999,479** because the receipt separately charged **321 raw PathUSD** for
   gas. The transaction used **200,209 gas units**; those units are not the
   same as the token charge. A receipt-based example would help developers
   compare swap output with wallet balance changes without calling a correct
   quote wrong or subtracting gas twice. [Receipt analysis](ADMISSION_REPORT.md)
5. **Publish a runnable boundary for the public routing example.** The
   inspected `uniroute-public` checkout lacks `package.json`, `src/models`,
   `src/lib/helpers.ts` (including `isTempoAggHook`) and
   `src/lib/methodParameters.ts`. We could prepare and mock-test a patch, but
   could not run the full service or verify its production hook allowlist,
   final calldata builder or route ranking. A minimal runnable integration
   fixture would make external contributions much easier to validate.

## Evidence limits

The real-contract measurements above come from a historical local fork, not a
live quote service or a Tempo mainnet transaction we broadcast. The ordinary
route comparison control uses boundary mocks. We have not measured how often
production users encounter this condition, whether the current Uniswap app
selects a worse route, or whether this route beats a validated competing route
after gas. The prototype supports only the checked Tempo v1.0 deployment and
route shapes at the recorded block; it does not establish behavior for other
hooks, blocks, chains or exact-output swaps. The public TypeScript patch still
needs a real plan builder and validator connected to the private UniRoute
service before it can admit candidates there.
