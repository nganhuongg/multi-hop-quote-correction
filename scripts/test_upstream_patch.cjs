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

  const metrics = {count: async () => {}, dist: async () => {}};
  const ctx = {logger: {warn: () => {}, debug: () => {}}, metrics};
  const blockHash = '0x' + 'ab'.repeat(32);
  const manager = '0x33620f62c5b9b2086dd6b62f4a297a9f30347029';
  const feeCollector = '0xfeec000000000000000000000000000000000000';
  const plan = {to: '0xrouter', from: '0xpayer', data: '0x1234', value: '0x0',
    recipient: '0xpayer', deadline: 1790346234, minimumOutput: 24872511n};
  const boundary = (overrides = {}, planOverrides = {}) => ({
    buildPlan: async request => {
      assert.equal(request.blockHash, blockHash);
      return {...plan, ...planOverrides};
    },
    validate: async (request, executionPlan) => ({
      status: 'success', routeKey: request.routeKey, amountIn: request.amountIn,
      chainId: request.chainId, blockNumber: request.blockNumber,
      blockHash: request.blockHash, planKey: exports.tempoPlanKey(executionPlan),
      grossOutputTransfer: request.quotedAmountOut,
      recipientDelta: request.quotedAmountOut,
      feePayer: executionPlan.from, feeToken: pathUsd,
      feeTokenTransfers: [{from: executionPlan.from, to: feeCollector, amount: 7n}],
      outputTokenTransfers: [{from: manager, to: executionPlan.recipient,
        amount: request.quotedAmountOut}],
      ...overrides,
    }),
  });
  async function fetch(route, amount, admission, outputs) {
    const calls = [];
    const values = [...outputs];
    const factory = () => ({callStatic: {quote: async (direction, specified, poolId, options) => {
      calls.push({direction, amount: specified, poolId, options});
      return {toBigInt: () => values.shift()};
    }}});
    const quotes = await exports.fetchAggHookQuotes(
      {chainId: 4217}, [route], amount, TradeType.ExactIn, input,
      new Map([[4217, {getBlock: async () => ({hash: blockHash})}]]),
      ctx, [], factory, 41183156, admission
    );
    return {quotes, calls};
  }
  const {quotes, calls} = await fetch(tempoRoute, 25000000n, boundary(),
    [24995000n, 24997499n]);
  assert.equal(quotes.length, 1);
  assert.equal(quotes[0].amount, 24997499n);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].direction, false);
  assert.equal(calls[0].amount, -25000000n);
  assert.equal(calls[1].direction, true);
  assert.equal(calls[1].amount, -24995000n);
  assert.deepEqual(calls.map(x => x.options.blockTag), [41183156, 41183156]);
  assert.deepEqual(calls.map(x => x.poolId), pools.map(x => x.poolId));
  const unavailable = await fetch(tempoRoute, 25000000n, undefined,
    [24995000n, 24997499n]);
  assert.equal(unavailable.quotes.length, 0);
  assert.equal(unavailable.calls.length, 0);
  for (const invalid of [
    {status: 'failed'}, {routeKey: 'other route'}, {amountIn: 1n},
    {blockNumber: 41183157}, {blockHash: '0xdead'},
    {planKey: 'different plan'}, {recipientDelta: 24997498n},
    {grossOutputTransfer: 24997498n},
  ]) {
    const rejected = await fetch(tempoRoute, 25000000n, boundary(invalid),
      [24995000n, 24997499n]);
    assert.equal(rejected.quotes.length, 0, `invalid validation admitted: ${Object.keys(invalid)}`);
  }
  const single = {path: [pools[0]], percentage: 100};
  const pathUsdNet = await fetch(single, 1000000n,
    boundary({recipientDelta: 999479n,
      feeTokenTransfers: [{from: plan.from, to: feeCollector, amount: 321n}]}), [999800n]);
  assert.equal(pathUsdNet.quotes.length, 1, 'receipt-proven gas must restore gross swap output');
  const other = '0x1111111111111111111111111111111111111111';
  const separate = await fetch(single, 1000000n, boundary({}, {recipient: other}), [999800n]);
  assert.equal(separate.quotes.length, 1, 'payer gas must not reduce a separate recipient output');
  const otherGasToken = await fetch(single, 1000000n,
    boundary({feeToken: cUsd, feeTokenTransfers: []}), [999800n]);
  assert.equal(otherGasToken.quotes.length, 1);
  const unknownFee = await fetch(single, 1000000n,
    boundary({recipientDelta: 999479n, feeTokenTransfers: []}), [999800n]);
  assert.equal(unknownFee.quotes.length, 0, 'unknown fee must leave quote ineligible');
  const shortOutput = await fetch(single, 1000000n,
    boundary({grossOutputTransfer: 999799n, recipientDelta: 999799n,
      outputTokenTransfers: [{from: manager, to: plan.recipient, amount: 999799n}]}),
    [999800n]);
  assert.equal(shortOutput.quotes.length, 0, 'actual output shortfall must be rejected');
  const deep = fs.readFileSync(path.join(temporary, 'src/core/strategy/DeepQuoteStrategy.ts'), 'utf8');
  assert.ok(deep.includes('this.tempoAdmissionBoundary'));
  console.log('PASS: patch applies; normal partition unchanged; pinned hop composition; receipt-based recipient output and bound admission');
} finally {
  fs.rmSync(temporary, {recursive: true, force: true});
}

}

main().catch(error => { console.error(error); process.exitCode = 1; });
