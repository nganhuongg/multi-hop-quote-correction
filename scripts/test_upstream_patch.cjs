// Focused executable boundary test for the patch against the public checkout.
// The public repository lacks several imported modules, so only external
// module interfaces are mocked; the patched AggHookQuoter source runs intact.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

async function main() {
const upstream = process.env.UNIROUTE_PUBLIC_DIR;
if (!upstream) throw new Error('Set UNIROUTE_PUBLIC_DIR to the uniroute-public checkout');
const root = path.resolve(__dirname, '..');
const patch = path.join(root, 'patches/uniroute-tempo-multihop.patch');
const expectedCommit = '2961efa8d44b80d353ee3af82cf868702bb6ab6a';
const commit = execFileSync('git', ['-C', upstream, 'rev-parse', 'HEAD'], {encoding: 'utf8'}).trim();
assert.equal(commit, expectedCommit, 'upstream baseline changed');
execFileSync('git', ['-C', upstream, 'apply', '--check', patch]);

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tempo-upstream-patch-'));
try {
  for (const name of ['AggHookQuoter.ts', 'DeepQuoteStrategy.ts']) {
    const relative = path.join('src', 'core', 'strategy', name);
    const destination = path.join(temporary, relative);
    fs.mkdirSync(path.dirname(destination), {recursive: true});
    fs.copyFileSync(path.join(upstream, relative), destination);
  }
  execFileSync('git', ['-C', temporary, 'apply', patch]);

  // Use the installed TypeScript compiler; no private UniRoute dependencies
  // are required to transpile this isolated public source file.
  const compilerPath = fs.realpathSync(execFileSync('which', ['tsc'], {encoding: 'utf8'}).trim());
  const ts = require(path.dirname(path.dirname(compilerPath)));
  const source = fs.readFileSync(path.join(temporary, 'src/core/strategy/AggHookQuoter.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
    reportDiagnostics: true,
  });
  assert.equal(compiled.diagnostics.length, 0, 'TypeScript transpilation failed');

  class QuoteBasic {
    constructor(route, amount) { this.route = route; this.amount = amount; }
  }
  const TradeType = {ExactIn: 'ExactIn', ExactOut: 'ExactOut'};
  const modules = {
    ethers: {ethers: {Contract: class {}}},
    '../../models/quote/QuoteBasic': {QuoteBasic},
    '../../models/quote/TradeType': {TradeType},
    '../../lib/config': {buildMetricKey: x => x, ChainId: {4217: 'TEMPO'}},
    '../../lib/helpers': {isTempoAggHook: pool => pool.hooks === hook},
    '../../../abis/AggHookQuoteABI': {AGG_HOOK_QUOTE_ABI: []},
  };
  const exports = {};
  vm.runInNewContext(compiled.outputText, {
    exports, require: name => {
      if (!(name in modules)) throw new Error(`Unexpected runtime import: ${name}`);
      return modules[name];
    },
    console, Map, Promise, BigInt, Date,
  }, {filename: 'AggHookQuoter.js'});

  const hook = '0x7169a78a59f136876e724b648fbb339a42f46888';
  const pathUsd = '0x20c0000000000000000000000000000000000000';
  const cUsd = '0x20c0000000000000000000000520792dcccccccc';
  const usdt0 = '0x20c00000000000000000000014f22ca97301eb73';
  const pools = [
    {poolId: '0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57',
      fee: 500, tickSpacing: 10, hooks: hook, token0: {address: pathUsd}, token1: {address: cUsd}},
    {poolId: '0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22',
      fee: 500, tickSpacing: 10, hooks: hook, token0: {address: pathUsd}, token1: {address: usdt0}},
  ];
  const tempoRoute = {path: pools, percentage: 100};
  const ordinaryRoute = {path: [{hooks: '0x0'}], percentage: 100};
  const input = {wrappedAddress: {address: cUsd}};
  const partition = exports.partitionAggHookRoutes(
    [tempoRoute, ordinaryRoute], 4217, TradeType.ExactIn, input, 41183156
  );
  assert.equal(partition.aggHookRoutes.length, 1);
  assert.equal(partition.otherRoutes.length, 1);
  assert.equal(partition.aggHookRoutes[0], tempoRoute);
  assert.equal(exports.isSupportedTempoMultiHopRoute(tempoRoute, 4217, TradeType.ExactIn, input, 41183157), false);
  assert.equal(exports.isSupportedTempoMultiHopRoute(tempoRoute, 4217, TradeType.ExactOut, input, 41183156), false);
  assert.equal(exports.isSupportedTempoMultiHopRoute(
    {path: [pools[0], {...pools[1], hooks: '0x0'}]}, 4217, TradeType.ExactIn, input, 41183156
  ), false);

  const calls = [];
  const factory = () => ({callStatic: {quote: async (direction, amount, poolId, options) => {
    calls.push({direction, amount, poolId, options});
    const output = calls.length === 1 ? 24995000n : 24997499n;
    return {toBigInt: () => output};
  }}});
  const metrics = {count: async () => {}, dist: async () => {}};
  const ctx = {logger: {warn: () => {}, debug: () => {}}, metrics};
  const quotes = await exports.fetchAggHookQuotes(
    {chainId: 4217}, [tempoRoute], 25000000n, TradeType.ExactIn, input,
    new Map([[4217, {}]]), ctx, [], factory, 41183156
  );
  assert.equal(quotes.length, 1);
  assert.equal(quotes[0].amount, 24997499n);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].direction, false);
  assert.equal(calls[0].amount, -25000000n);
  assert.equal(calls[1].direction, true);
  assert.equal(calls[1].amount, -24995000n);
  assert.deepEqual(calls.map(x => x.options.blockTag), [41183156, 41183156]);
  assert.deepEqual(calls.map(x => x.poolId), pools.map(x => x.poolId));
  console.log('PASS: patch applies; dispatch, unsupported scope, block pinning, and two-hop quote composition');
} finally {
  fs.rmSync(temporary, {recursive: true, force: true});
}

}

main().catch(error => { console.error(error); process.exitCode = 1; });
