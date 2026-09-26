# UniRoute public quote-dispatch patch

`uniroute-tempo-multihop.patch` applies to `Uniswap/uniroute-public` at
`2961efa8d44b80d353ee3af82cf868702bb6ab6a`. The external checkout was
left unchanged. The patch edits `AggHookQuoter.ts` and `DeepQuoteStrategy.ts`:

- The existing single-hop hook path remains available.
- Exact-input cUSD -> PathUSD -> USDT0/USDC.e two-hop routes using the verified
  Tempo v1.0 hook, pool IDs, fee, tick spacing, and block 41,183,156 are sent to
  `hook.quote()` in hop order. Both reads use the requested block tag.
- Ordinary routes stay with `fetchQuotes`. Unsupported Tempo shapes are not
  promoted to the specialized path.
- The resulting `QuoteBasic` enters the strategy's existing quote merge. It is
  a **candidate** at that boundary, not proof that UniRoute's final calldata
  executes. The independent Python dispatcher gates its comparison input on a
  complete local-fork Universal Router transaction.

From this project root, with a separate public checkout:

```bash
export UNIROUTE_PUBLIC_DIR=/absolute/path/to/uniroute-public
git -C "$UNIROUTE_PUBLIC_DIR" rev-parse HEAD
git -C "$UNIROUTE_PUBLIC_DIR" apply --check "$PWD/patches/uniroute-tempo-multihop.patch"
node scripts/test_upstream_patch.cjs
# To inspect the edit on a disposable copy only:
# git -C /path/to/disposable/uniroute-public apply "$PWD/patches/uniroute-tempo-multihop.patch"
```

The Node test copies two source files to a temporary directory, applies the
patch there, transpiles `AggHookQuoter.ts` with an installed `tsc`, and runs its
actual exported functions with mocks only for missing imported modules and
contract responses. It checks classification, exact-input scope, block
propagation, and the second hop receiving the first hop's output. It does not
prove the whole `DeepQuoteStrategy` or private UniRoute service executes.

The public checkout lacks `package.json`, `src/models`,
`src/lib/helpers.ts`, and `src/lib/methodParameters.ts`; full typechecking and
service integration cannot be run from this checkout. The patch is a concrete
upstream quote-dispatch change, **not** a production-ready integration: the
service still needs a final Universal Router execution-validation gate and a
decision on current-block support. The pinned historical block deliberately
prevents claiming arbitrary-block deployment or liquidity validity. Shared
liquidity compositions, exact output, other hooks, and other chains remain out
of scope.
