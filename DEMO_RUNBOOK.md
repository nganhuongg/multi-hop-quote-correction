# Reproduce the recorded quote-admission demo

Run from the project root with Python 3.12+, Foundry `anvil` and `cast`, and
access to a Tempo archive RPC that serves block **41,183,156** (chain 4217,
hash `0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3`).
The active Python package needs no sibling checkout. A fork must support
`evm_snapshot`, `anvil_dealTIP20`, impersonation and `debug_traceCall`.

Install once in the project root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

In terminal 1, start a **fresh** local fork. Replace the RPC URL with your
archive endpoint if necessary; never put a credentialed URL in a committed
file.

```bash
export PATH="$HOME/.foundry/bin:$PATH"
export TEMPO_ARCHIVE_RPC=https://rpc.tempo.xyz
anvil --fork-url "$TEMPO_ARCHIVE_RPC" --fork-block-number 41183156 \
  --timestamp 1790342634 --port 8549 --silent
```

In terminal 2, run the focused controls and both local-fork demos:

```bash
export PATH="$HOME/.foundry/bin:$PATH"
export TEMPO_FORK_RPC=http://127.0.0.1:8549
.venv/bin/python -m unittest discover -s tests -p test_dispatch.py -v
.venv/bin/python -m unittest discover -s tests -p test_tempo_fork.py -v
.venv/bin/python dispatch_demo.py --rpc "$TEMPO_FORK_RPC" --target USDT0 --amount 25
.venv/bin/python dispatch_demo.py --rpc "$TEMPO_FORK_RPC" --target PathUSD --amount 1
```

The [Solution dashboard](dashboard/index.html#solution) displays the three
recorded Anvil cases immediately. Selecting a case changes the displayed
before/after quote and funded execution result; viewers do not need Anvil or
an RPC endpoint. The saved records and fork provenance are in
[`dashboard/solution-results.js`](dashboard/solution-results.js).

To independently remeasure all three dashboard cases, keep the fresh fork
running and execute each case from the project root:

```bash
export TEMPO_FORK_RPC=http://127.0.0.1:8549
.venv/bin/python dashboard_proof.py --rpc "$TEMPO_FORK_RPC" --case small
.venv/bin/python dashboard_proof.py --rpc "$TEMPO_FORK_RPC" --case gap
.venv/bin/python dashboard_proof.py --rpc "$TEMPO_FORK_RPC" --case illiquid
```

The case runner measures the baseline quote, composes the hook quote, builds
the funded plan, executes the deployed Router, reads the receipt and recipient
balance, and reverts the snapshot. The 1,000,000-cUSD control returns
`InsufficientLiquidity()` from the hook quote. Its zero-minimum-output Router
plan is a diagnostic probe: the funded transaction reverts with receipt status
0, and the plan is never admitted as a quote. If `cast` is not on Python's
`PATH`, set `FOUNDRY_CAST` to its absolute executable path.

| Case | Evidence and expected result |
|---|---|
| Ordinary route | `DispatchTests.test_recovered_route_reaches_comparison_with_standard_candidate` exercises ordinary and Tempo candidate admission together using **boundary mocks**. It is not an ordinary-route fork measurement. |
| 25 cUSD → PathUSD → USDT0 | **Real Tempo fork**: standard V4Quoter reverts; specialized quote is **24,997,499 raw USDT0**; full Universal Router transaction produces the same recipient output, uses **316,216 receipt gas units**, and admits the candidate. Recorded JSON: [`demo-results/dispatch_25_cusd.json`](demo-results/dispatch_25_cusd.json). |
| 1 cUSD → PathUSD | **Real Tempo fork**: the swap sends **999,800 raw PathUSD**. The payer-recipient wallet rises **999,479**, while the transaction receipt proves a separate **321 raw PathUSD gas charge**. The reconciled candidate is admitted. Receipt gas usage is **200,209 units**, a different measure from the 321-token charge. Recorded JSON: [`demo-results/dispatch_pathusd_1_cusd.json`](demo-results/dispatch_pathusd_1_cusd.json) and [`demo-results/pathusd_fee_diagnostic.json`](demo-results/pathusd_fee_diagnostic.json). |

The timestamp is the recorded parent-block timestamp. The Router plan deadline
is 3,600 seconds later. Anvil may use the host clock for the next transaction
if `--timestamp` is omitted; then the historical plan can revert even though
the pinned quote still succeeds. Use an unused port so a stale Anvil process
cannot silently receive the demo commands.

The demo scripts snapshot and revert transactions on the **local fork**; they
do not broadcast to Tempo. For the 25-cUSD case, the fixture sets only the
test payer's cUSD balance to 30 cUSD and native balance to 1 ETH. It does not
top up PoolManager or Tempo Exchange. The historical execution plan has a
deadline tied to the fork block, so use a fresh fork if the transaction expires.
`--output /path/to/result.json` optionally saves full Router calldata and
measurements; avoid overwriting the committed recorded results while checking
the demo.

All tests can be run with `.venv/bin/python -m unittest discover -s tests -v`.
The proposed public UniRoute patch has a separate optional boundary test:

```bash
UNIROUTE_PUBLIC_DIR=/absolute/path/to/uniroute-public node scripts/test_upstream_patch.cjs
```

That command requires Node.js, `tsc` in `PATH`, and an explicit public
UniRoute checkout at commit `2961efa8d44b80d353ee3af82cf868702bb6ab6a`.
It uses mocks because the public checkout lacks the private production service
components. This is a standalone validated prototype plus a proposed patch,
not a deployed or end-to-end runnable UniRoute service. Missing or ambiguous
execution evidence leaves a candidate indeterminate and ineligible; an actual
swap-output shortfall fails validation. No measured net-price advantage over a
validated competing real route is claimed.
