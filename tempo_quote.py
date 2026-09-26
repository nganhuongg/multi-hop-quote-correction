"""Narrow exact-input Tempo v4 quote and Universal Router adapter.

Only the pinned Tempo v1.0 deployment and tested route shapes are supported.
Independent hook quotes are *candidates*: full-router validation is separate.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CHAIN_ID = 4217
BLOCK = 41_183_156
BLOCK_HASH = "0xf6c6323efefde7d64d544512326ea00ab1d3f0cf75bddd55e7699596ee4123c3"
HOOK = "0x7169a78a59f136876e724b648fbb339a42f46888"
MANAGER = "0x33620f62c5b9b2086dd6b62f4a297a9f30347029"
QUOTER = "0x20e6487c371a2086f841ef453f85378223df4f4e"
ROUTER = "0x182a927119d56008d921126764bf884221b10f59"
PAYER = "0xf9efc19218e6a9e58df5767ffa627f37de2bf7cc"
TOKENS = {
    "PathUSD": "0x20c0000000000000000000000000000000000000",
    "cUSD": "0x20c0000000000000000000000520792dcccccccc",
    "USDT0": "0x20c00000000000000000000014f22ca97301eb73",
    "USDC.e": "0x20c000000000000000000000b9537d11c60e8b50",
}
POOLS = {
    "cUSD": "0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57",
    "USDT0": "0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22",
    "USDC.e": "0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588",
}
SUPPORTED = {
    ("cUSD", "PathUSD"),
    ("cUSD", "USDT0"),
    ("cUSD", "USDC.e"),
}
FEE = 500
TICK_SPACING = 10
EMPTY_HOOK_DATA = "0x"


class UnsupportedRoute(ValueError):
    pass


class RpcError(RuntimeError):
    pass


class TempoClient:
    """JSON-RPC boundary: every read receives the same explicit block tag."""

    def __init__(self, url: str):
        self.url = url
        self.count = 0
        self._selectors: dict[str, str] = {}

    def rpc(self, method: str, params: list):
        self.count += 1
        data = json.dumps({"jsonrpc": "2.0", "id": self.count, "method": method, "params": params}).encode()
        request = urllib.request.Request(self.url, data, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                answer = json.load(response)
        except Exception as exc:
            raise RpcError(f"{method}: {exc}") from exc
        if "error" in answer:
            raise RpcError(f"{method}: {answer['error']}")
        return answer["result"]

    def selector(self, signature: str) -> str:
        if signature not in self._selectors:
            self._selectors[signature] = self.rpc("web3_sha3", ["0x" + signature.encode().hex()])[:10]
        return self._selectors[signature]

    def pinned_block(self, context: "BlockContext") -> dict:
        if int(self.rpc("eth_chainId", []), 16) != context.chain_id:
            raise RpcError("wrong chain ID")
        block = self.rpc("eth_getBlockByNumber", [context.tag, False])
        if not block or block["hash"].lower() != context.hash.lower():
            raise RpcError("fork is not pinned to the verified Tempo block")
        return block

    def balance(self, token: str, owner: str, block: str = "latest") -> int:
        data = "0x70a08231" + int(owner, 16).to_bytes(32, "big").hex()
        return int(self.rpc("eth_call", [{"to": token, "data": data}, block]), 16)


@dataclass(frozen=True)
class BlockContext:
    chain_id: int
    number: int
    hash: str

    @property
    def tag(self) -> str:
        return hex(self.number)


HISTORICAL_CONTEXT = BlockContext(CHAIN_ID, BLOCK, BLOCK_HASH)


@dataclass(frozen=True)
class PoolKey:
    currency0: str
    currency1: str
    fee: int
    tick_spacing: int
    hooks: str
    pool_id: str


VERIFIED_POOL_KEYS = {
    token: PoolKey(TOKENS["PathUSD"], TOKENS[token], FEE, TICK_SPACING, HOOK, pool_id)
    for token, pool_id in POOLS.items()
}


@dataclass(frozen=True)
class Hop:
    source: str
    target: str
    pool_key: PoolKey
    zero_for_one: bool
    hook_data: str = EMPTY_HOOK_DATA

    @property
    def pool_id(self) -> str:
        return self.pool_key.pool_id


@dataclass(frozen=True)
class RouteDescription:
    source: str
    target: str
    hops: tuple[Hop, ...]

    @property
    def label(self) -> str:
        return " -> ".join([self.source] + [hop.target for hop in self.hops])


def resolve_route(source: str, target: str) -> RouteDescription:
    """Historical, verified route fixtures; not an arbitrary route finder."""
    if (source, target) not in SUPPORTED:
        raise UnsupportedRoute(f"unsupported exact-input route: {source} -> {target}")
    names = [source, target] if "PathUSD" in (source, target) else [source, "PathUSD", target]
    hops = []
    for left, right in zip(names, names[1:]):
        external = right if left == "PathUSD" else left
        hops.append(Hop(left, right, VERIFIED_POOL_KEYS[external], left == "PathUSD"))
    return RouteDescription(source, target, tuple(hops))


def validate_supported_route(route: RouteDescription, context: BlockContext) -> None:
    """Enforce the checked deployment, pool keys, direction, and route structure."""
    if context != HISTORICAL_CONTEXT:
        raise UnsupportedRoute("only the verified Tempo chain and block are supported")
    if (route.source, route.target) not in SUPPORTED:
        raise UnsupportedRoute(f"unsupported exact-input route: {route.source} -> {route.target}")
    expected = resolve_route(route.source, route.target)
    if route != expected:
        raise UnsupportedRoute("route token continuity, pool key, hook, direction, or hook data is unsupported")
    if len({hop.pool_id for hop in route.hops}) != len(route.hops):
        raise UnsupportedRoute("shared pool liquidity composition is not validated")


def quote_candidate(client: TempoClient, route: RouteDescription, amount: int,
                    context: BlockContext) -> dict:
    validate_supported_route(route, context)
    if amount <= 0 or amount >= 2**127:
        raise ValueError("amount must be positive and fit the hook exact-input range")
    started, count = time.perf_counter(), client.count
    client.pinned_block(context)
    current = amount
    legs = []
    for hop in route.hops:
        data = (
            client.selector("quote(bool,int256,bytes32)")
            + int(hop.zero_for_one).to_bytes(32, "big").hex()
            + ((-current) % (1 << 256)).to_bytes(32, "big").hex()
            + hop.pool_id[2:]
        )
        output = int(client.rpc("eth_call", [{"to": hop.pool_key.hooks, "data": data}, context.tag]), 16)
        legs.append({"source": hop.source, "target": hop.target, "poolId": hop.pool_id,
                     "poolKey": {"currency0": hop.pool_key.currency0,
                                 "currency1": hop.pool_key.currency1,
                                 "fee": hop.pool_key.fee,
                                 "tickSpacing": hop.pool_key.tick_spacing,
                                 "hooks": hop.pool_key.hooks},
                     "zeroForOne": hop.zero_for_one, "hookData": hop.hook_data,
                     "amountIn": current, "amountOut": output})
        current = output
    return {"status": "candidate", "source": route.source, "target": route.target,
            "route": route.label, "amountIn": amount,
            "amountOut": current, "chainId": context.chain_id,
            "block": context.number, "blockHash": context.hash,
            "hook": HOOK, "decimals": 6, "hops": legs,
            "composition": "independent hook quotes; execution validation required",
            "quoteMetrics": {"rpcCalls": client.count - count,
                             "elapsedMs": round((time.perf_counter() - started) * 1000, 1)}}


def _cast(mode: str, signature: str, *args: str) -> str:
    binary = shutil.which("cast") or str(Path.home() / ".foundry/bin/cast")
    return subprocess.check_output([binary, mode, signature, *args], text=True).strip()


def build_plan(candidate: dict, route: RouteDescription, amount: int,
               context: BlockContext, payer: str, recipient: str, deadline: int,
               slippage_bps: int = 50) -> dict:
    """Build the public SwapStepsFactory's SETTLE -> SWAP -> TAKE V4 command.

    Caller must already have a valid Permit2 allowance to Universal Router.
    No on-chain Permit2 signature is manufactured here. Existing allowance is
    checked by full-router simulation; adapters may prepend a real permit.
    """
    if candidate["status"] != "candidate" or not 0 <= slippage_bps <= 10_000:
        raise ValueError("invalid candidate or slippage")
    validate_supported_route(route, context)
    source, target = route.source, route.target
    if (candidate.get("source"), candidate.get("target"), candidate.get("amountIn")) != (source, target, amount):
        raise ValueError("candidate route or input amount is inconsistent")
    if (candidate.get("chainId") != context.chain_id or candidate.get("block") != context.number
            or candidate.get("blockHash") != context.hash or candidate.get("hook") != HOOK):
        raise UnsupportedRoute("candidate is not from the verified deployment and block")
    legs = candidate.get("hops", [])
    if len(legs) != len(route.hops):
        raise UnsupportedRoute("candidate path does not match the verified route")
    running = amount
    for leg, known in zip(legs, route.hops):
        expected_key = {"currency0": known.pool_key.currency0,
                        "currency1": known.pool_key.currency1,
                        "fee": known.pool_key.fee,
                        "tickSpacing": known.pool_key.tick_spacing,
                        "hooks": known.pool_key.hooks}
        if (leg["source"], leg["target"], leg["poolId"], leg["poolKey"],
                leg["zeroForOne"], leg["hookData"], leg["amountIn"]) != (
            known.source, known.target, known.pool_id, expected_key,
            known.zero_for_one, known.hook_data, running
        ):
            raise UnsupportedRoute("candidate hop or chained amount is unsupported")
        running = leg["amountOut"]
    if running != candidate["amountOut"] or running <= 0:
        raise ValueError("candidate output is inconsistent")
    minimum = candidate["amountOut"] * (10_000 - slippage_bps) // 10_000
    path = "[" + ",".join(
        f"({TOKENS[hop.target]},{hop.pool_key.fee},{hop.pool_key.tick_spacing},"
        f"{hop.pool_key.hooks},{hop.hook_data})" for hop in route.hops
    ) + "]"
    swap = _cast("abi-encode", "f((address,(address,uint24,int24,address,bytes)[],uint256[],uint128,uint128))",
                 f"({TOKENS[source]},{path},[],{amount},{minimum})")
    settle = _cast("abi-encode", "f(address,uint256,bool)", TOKENS[source], str(amount), "true")
    take = _cast("abi-encode", "f(address,address,uint256)", TOKENS[target], recipient, "0")
    v4 = _cast("abi-encode", "f(bytes,bytes[])", "0x0b070e", f"[{settle},{swap},{take}]")
    calldata = _cast("calldata", "execute(bytes,bytes[],uint256)", "0x10", f"[{v4}]", str(deadline))
    return {"to": ROUTER, "from": payer, "data": calldata, "value": "0x0",
            "minimumOutput": minimum, "deadline": deadline, "recipient": recipient,
            "payer": payer, "actions": ["SETTLE", "SWAP_EXACT_IN", "TAKE"],
            "permit2Assumption": "payer has sufficient existing Permit2 allowance to Universal Router"}


def standard_quote(client: TempoClient, route: RouteDescription, amount: int,
                   context: BlockContext) -> dict:
    validate_supported_route(route, context)
    path = "[" + ",".join(
        f"({TOKENS[hop.target]},{hop.pool_key.fee},{hop.pool_key.tick_spacing},"
        f"{hop.pool_key.hooks},{hop.hook_data})" for hop in route.hops
    ) + "]"
    data = _cast("calldata", "quoteExactInput((address,(address,uint24,int24,address,bytes)[],uint128))",
                 f"({TOKENS[route.source]},{path},{amount})")
    try:
        raw = client.rpc("eth_call", [{"from": PAYER, "to": QUOTER, "data": data}, context.tag])
        return {"status": "success", "amountOut": int(raw[2:66], 16), "gasEstimate": int(raw[66:130], 16)}
    except RpcError as exc:
        return {"status": "revert", "error": str(exc)}


def _hook_calls(node: dict) -> int:
    return int(node.get("to", "").lower() == HOOK) + sum(_hook_calls(child) for child in node.get("calls", []))


def _recipient_transfers(node: dict, token: str, recipient: str) -> list[int]:
    transfers = []
    data = node.get("input", "")
    if node.get("to", "").lower() == token.lower() and data.startswith("0xa9059cbb") and len(data) >= 138:
        if ("0x" + data[34:74]).lower() == recipient.lower():
            transfers.append(int(data[74:138], 16))
    for child in node.get("calls", []):
        transfers.extend(_recipient_transfers(child, token, recipient))
    return transfers


def run_fork_route_case(client: TempoClient, route: RouteDescription, amount: int,
                        context: BlockContext, payer: str = PAYER,
                        recipient: str = PAYER) -> dict:
    """Quote, simulate and locally execute from one fork snapshot; always revert.

    Anvil-only methods are required. The real deployed contracts are used.
    Only the test payer's input TIP-20 and gas balance may be topped up.
    """
    if not client.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise RpcError("fork execution requires a loopback Anvil endpoint")
    validate_supported_route(route, context)
    source, target = route.source, route.target
    block = client.pinned_block(context)
    if int(client.rpc("eth_blockNumber", []), 16) != context.number:
        raise RpcError("fresh fork required: local chain has advanced")
    started, count = time.perf_counter(), client.count
    snapshot = client.rpc("evm_snapshot", [])
    funding = []
    impersonated = False
    result = None
    try:
        manager_before = client.balance(TOKENS[source], MANAGER)
        wallet_before = client.balance(TOKENS[source], payer)
        if wallet_before < amount:
            funded = max(amount, 30_000_000)
            client.rpc("anvil_dealTIP20", [payer, TOKENS[source], hex(funded)])
            funding.append({"account": payer, "token": source, "balanceSetTo": funded})
        gas_before = int(client.rpc("eth_getBalance", [payer, "latest"]), 16)
        if gas_before < 10**18:
            client.rpc("anvil_setBalance", [payer, hex(10**18)])
            funding.append({"account": payer, "nativeGasBalanceSetTo": 10**18})
        if client.balance(TOKENS[source], MANAGER) != manager_before:
            raise RpcError("PoolManager balance changed during payer-only setup")
        std = standard_quote(client, route, amount, context)
        result = {"chainId": context.chain_id, "parentBlock": context.number,
                  "blockHash": context.hash, "route": route.label,
                  "amountIn": amount, "decimals": 6, "poolManagerInputBalance": manager_before,
                  "payerInputBalanceBeforeFunding": wallet_before, "testFunding": funding,
                  "standardQuote": std}
        try:
            candidate = quote_candidate(client, route, amount, context)
        except RpcError as exc:
            result.update(candidate={"status": "revert", "error": str(exc)},
                          execution={"status": "not-attempted", "reason": "direct hook quote failed"})
            return result
        result["candidate"] = candidate
        deadline = int(block["timestamp"], 16) + 3600
        plan = build_plan(candidate, route, amount, context, payer, recipient, deadline)
        result["plan"] = plan
        tx = {k: plan[k] for k in ("to", "from", "data", "value")}
        try:
            client.rpc("eth_call", [tx, context.tag])
            trace = client.rpc("debug_traceCall", [tx, context.tag, {"tracer": "callTracer"}])
        except RpcError as exc:
            result["execution"] = {"status": "revert", "phase": "eth_call", "error": str(exc)}
            return result
        hook_calls = _hook_calls(trace)
        if hook_calls != len(candidate["hops"]):
            raise RpcError(f"trace had {hook_calls} hook calls; expected {len(candidate['hops'])}")
        gross_transfers = _recipient_transfers(trace, TOKENS[target], recipient)
        if len(gross_transfers) != 1:
            raise RpcError(f"expected one output transfer to recipient, found {gross_transfers}")
        recipient_before = client.balance(TOKENS[target], recipient)
        client.rpc("anvil_impersonateAccount", [payer])
        impersonated = True
        tx["gas"] = hex(2_000_000)
        tx_hash = client.rpc("eth_sendTransaction", [tx])  # local Anvil only
        receipt = None
        for _ in range(100):
            receipt = client.rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
            time.sleep(0.1)
        if not receipt or int(receipt["status"], 16) != 1:
            result["execution"] = {"status": "revert", "phase": "local transaction", "txHash": tx_hash,
                                    "receipt": receipt}
            return result
        delta = client.balance(TOKENS[target], recipient) - recipient_before
        gross = gross_transfers[0]
        result["execution"] = {"status": "success", "grossOutputTransfer": gross,
                                "recipientDelta": delta, "netVsGross": delta - gross,
                                "matchesQuote": gross == candidate["amountOut"],
                                "roundingDifference": gross - candidate["amountOut"],
                                "gasUsed": int(receipt["gasUsed"], 16), "hookCalls": hook_calls,
                                "preflightTraceGasUsed": int(trace.get("gasUsed", "0x0"), 16),
                                "effectiveGasPrice": int(receipt.get("effectiveGasPrice", "0x0"), 16),
                                "localForkTxHash": tx_hash}
        return result
    finally:
        if impersonated:
            client.rpc("anvil_stopImpersonatingAccount", [payer])
        client.rpc("evm_revert", [snapshot])
        if result is not None:
            result["metrics"] = {"rpcCalls": client.count - count,
                                 "elapsedMs": round((time.perf_counter() - started) * 1000, 1)}


def run_fork_case(client: TempoClient, source: str, target: str, amount: int,
                  payer: str = PAYER, recipient: str = PAYER) -> dict:
    """Compatibility entry point for the original historical regression CLI."""
    return run_fork_route_case(client, resolve_route(source, target), amount,
                               HISTORICAL_CONTEXT, payer, recipient)
