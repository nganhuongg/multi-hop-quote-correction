# Baseline evidence (before implementation)

These are copies of the existing investigation in `uniswap-v4-study`; they were not rerun to create this contribution. `quote-harness/results.txt` records 13 local tests, including expected failures. Its Tempo Exchange is a mock. `quote-harness/REAL_TEMPO_REPORT.md` links the read-only Tempo RPC probes, historical receipt/replays, and local Anvil fork simulations. `quote-harness/tempo_fork_usecases_clean_41183156.jsonl` and `quote-harness/tempo_fork_trace_25m_clean.json` record the real Tempo contracts on a fork. The fork changed only the payer's cUSD balance; it did not fund PoolManager or Tempo Exchange. No transactions were broadcast to Tempo.

The archived Foundry test relies on the original `uniswap-v4-study` source checkouts and library layout. It is preserved as evidence, not made into a standalone test dependency of this contribution; the new fork regression is under `tests/`.

The pinned parent block is 41,183,156 (`0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3`). Other inspected blocks: 41,115,563 (`0x0e7fb249fc4a847e0330fb38e34abe6419ab05236d817a55b8e027053c44dd4b`) and 41,274,562 (`0x5f1f7c995db46108dfecb8dd4672469162694d6cf506474c22e16cac091a085c`). Chain ID: 4217. All four listed TIP-20 tokens have six decimals at block 41,274,562. Deployment and pool addresses appear in `quote-harness/REAL_TEMPO_REPORT.md` and the linked inventories.

At the threshold, V4Quoter was directly measured to succeed for 19,862,459 raw cUSD and fail for 19,862,460. The **25,000,000 raw cUSD V4Quoter failure was also directly measured** in `tempo_fork_usecases_clean_41183156.jsonl`, not merely extrapolated from the threshold. At 25,000,000 raw cUSD, the real Universal Router with settlement before swap returned 24,997,499 raw USDT0 by trace, with 571,946 gas. This trace-based transfer is not an observed recipient balance delta; the new regression will measure that separately.

Source checkouts used: v4-core `46c6834698c48bc4a463a86d8420f4eb1d7f3b75`, v4-periphery `9969eec44cfdf07e24b41de47f40276a58401976`, v4-hooks-public `e4eabe526f9b516fff78d98ba781251747f0fd6e`, uniroute-public `2961efa8d44b80d353ee3af82cf868702bb6ab6a`, universal-router `543e1a19d6e21e31ced2512eec5792b50f13a0ba`.

To reproduce the read-only baseline from this repository (Python 3 and Foundry `cast` required):

```bash
cd evidence/quote-harness
python3 tempo_multihop_replay.py --source cusd --target usdt0 --block 41183156 --amount 1000000 --trace
```

For the fork baseline, start Anvil in another terminal, then run the script from `evidence/quote-harness`; it makes only local RPC calls:

```bash
anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8547 --silent
python3 tempo_fork_usecases.py --rpc http://127.0.0.1:8547 --trace-file /tmp/tempo_trace.json
```

The public UniRoute checkout lacks `src/lib/helpers.ts` (including `isTempoAggHook`), `src/lib/methodParameters.ts`, and `src/models`. Its full service cannot be run from these sources. The implementation in this repository therefore has an explicit integration boundary; no production selection or user losses are inferred from these artifacts.
