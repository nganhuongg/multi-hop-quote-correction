"""Read-only Tempo RPC probe for deployed Uniswap aggregator hooks.

Finds deployment blocks and pool registrations, then samples hook quotes at a
pinned block. It never sends transactions or changes chain state.
"""

import argparse
import hashlib
import json
import requests


HOOKS = {
    "routing_api_previous": "0x2929d242c6c475f78ea7ce8837c9078bcd9ca088",
    "routing_api": "0x717c31c3ea5f9070297f239fafd63d21afdaa888",
    "v4_subgraph": "0x7169a78a59f136876e724b648fbb339a42f46888",
}
REGISTERED = "AggregatorPoolRegistered(bytes32)"


class RPC:
    def __init__(self, url):
        self.url = url
        self.session = requests.Session()
        self.next_id = 0

    def call(self, method, params):
        self.next_id += 1
        response = self.session.post(
            self.url,
            json={"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"{method}: {data['error']}")
        return data["result"]

    def selector(self, signature):
        return self.call("web3_sha3", ["0x" + signature.encode().hex()])[:10]

    def topic(self, signature):
        return self.call("web3_sha3", ["0x" + signature.encode().hex()])

    def eth_call(self, address, data, block):
        return self.call("eth_call", [{"to": address, "data": data}, hex(block)])


def decode_string(result):
    raw = bytes.fromhex(result[2:])
    start = int.from_bytes(raw[:32], "big")
    size = int.from_bytes(raw[start : start + 32], "big")
    return raw[start + 32 : start + 32 + size].decode()


def deployment_block(rpc, address, latest):
    low, high = 0, latest
    while low < high:
        mid = (low + high) // 2
        if rpc.call("eth_getCode", [address, hex(mid)]) == "0x":
            low = mid + 1
        else:
            high = mid
    return low


def replay_transaction(rpc, tx_hash):
    tx = rpc.call("eth_getTransactionByHash", [tx_hash])
    receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
    block = int(tx["blockNumber"], 16) - 1
    if not tx.get("to"):
        print(json.dumps({"tx": tx_hash, "status": receipt["status"], "replay": "skipped: contract creation transaction"}))
        return
    request = {"from": tx["from"], "to": tx["to"], "data": tx["input"], "value": tx["value"], "gas": tx["gas"]}
    try:
        replay_result = rpc.call("eth_call", [request, hex(block)])
        replay = {"success": True, "returnData": replay_result}
    except RuntimeError as error:
        replay = {"success": False, "error": str(error)}
    print(json.dumps({"tx": tx_hash, "block": int(tx["blockNumber"], 16), "parentBlock": block, "index": int(tx["transactionIndex"], 16), "status": receipt["status"], "from": tx["from"], "to": tx["to"], "replay": replay}))
    swap_topic = rpc.topic("HookSwap(bytes32,address,int256,int256,uint24)")
    tokens_sig = rpc.selector("poolIdToTokens(bytes32)")
    quote_sig = rpc.selector("quote(bool,int256,bytes32)")
    balance_sig = rpc.selector("balanceOf(address)")
    manager = "0x33620f62c5b9b2086dd6b62f4a297a9f30347029"
    for log in receipt["logs"]:
        if log["topics"][0].lower() != swap_topic.lower():
            continue
        pool_id = log["topics"][1]
        hook = log["address"]
        words = [bytes.fromhex(log["data"][2+i*64:2+(i+1)*64]) for i in range(3)]
        amount0 = int.from_bytes(words[0], "big", signed=True)
        amount1 = int.from_bytes(words[1], "big", signed=True)
        token_result = rpc.eth_call(hook, tokens_sig + pool_id[2:], block)
        token0 = "0x" + token_result[26:66]
        token1 = "0x" + token_result[90:130]
        direction = amount0 > 0
        amount_in = amount0 if direction else amount1
        amount_out = -amount1 if direction else -amount0
        input_token = token0 if direction else token1
        manager_balance = int(rpc.eth_call(input_token, balance_sig + int(manager,16).to_bytes(32,"big").hex(), block),16)
        observations = {}
        for kind, amount in (("exactIn", -amount_in), ("exactOut", amount_out)):
            data = quote_sig + int(direction).to_bytes(32,"big").hex() + (amount % (1<<256)).to_bytes(32,"big").hex() + pool_id[2:]
            try:
                observations[kind] = int(rpc.eth_call(hook, data, block),16)
            except RuntimeError as error:
                observations[kind] = str(error)
        print(json.dumps({"poolId":pool_id,"hook":hook,"amount0":amount0,"amount1":amount1,"token0":token0,"token1":token1,"managerInputBalance":manager_balance,"observedInput":amount_in,"observedOutput":amount_out,"quotesAtParent":observations}))


def word(data, offset):
    return int.from_bytes(data[offset:offset+32], "big")


def abi_bytes(data, offset):
    size = word(data, offset)
    return data[offset+32:offset+32+size]


def abi_bytes_array(data, offset):
    count = word(data, offset)
    return [abi_bytes(data, offset+32+word(data, offset+32+i*32)) for i in range(count)]


def decode_transaction(rpc, tx_hash):
    tx = rpc.call("eth_getTransactionByHash", [tx_hash])
    data = bytes.fromhex(tx["input"][10:])
    commands = abi_bytes(data, word(data, 0))
    inputs = abi_bytes_array(data, word(data, 32))
    print(json.dumps({"tx": tx_hash, "commands": [hex(c & 0x3f) for c in commands]}))
    for command, param in zip(commands, inputs):
        if command & 0x3f != 0x10:
            continue
        actions = abi_bytes(param, word(param, 0))
        action_params = abi_bytes_array(param, word(param, 32))
        print(json.dumps({"v4Actions": [hex(x) for x in actions], "paramPrefixes": [p[:240].hex() for p in action_params]}))


def scan_actions_file(rpc, path):
    with open(path) as handle:
        batches = json.load(handle)
    hashes = list(dict.fromkeys(log["transactionHash"] for batch in batches for log in batch.get("result", []) if isinstance(batch.get("result"), list)))
    counts = {}
    samples = {}
    for tx_hash in hashes:
        tx = rpc.call("eth_getTransactionByHash", [tx_hash])
        if not tx.get("to") or tx["input"][:10] != "0x3593564c":
            continue
        data = bytes.fromhex(tx["input"][10:])
        commands = abi_bytes(data, word(data, 0))
        inputs = abi_bytes_array(data, word(data, 32))
        for command, param in zip(commands, inputs):
            if command & 0x3f != 0x10:
                continue
            actions = abi_bytes(param, word(param, 0))
            for action in actions:
                label = hex(action)
                counts[label] = counts.get(label, 0) + 1
                samples.setdefault(label, tx_hash)
    print(json.dumps({"transactions": len(hashes), "v4ActionCounts": counts, "sampleTxByAction": samples}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://rpc.tempo.xyz")
    parser.add_argument("--block", type=int, help="Pin all inventory and quote calls to a historical block")
    parser.add_argument("--replay-tx", action="append")
    parser.add_argument("--decode-tx")
    parser.add_argument("--scan-actions-file")
    args = parser.parse_args()
    rpc = RPC(args.rpc)
    if args.decode_tx:
        decode_transaction(rpc, args.decode_tx)
        return
    if args.scan_actions_file:
        scan_actions_file(rpc, args.scan_actions_file)
        return
    if args.replay_tx:
        for tx_hash in args.replay_tx:
            replay_transaction(rpc, tx_hash)
        return
    latest = args.block if args.block is not None else int(rpc.call("eth_blockNumber", []), 16)
    version_sig = rpc.selector("aggregatorHookVersion()")
    exchange_sig = rpc.selector("tempoExchange()")
    registered_topic = rpc.topic(REGISTERED)
    quote_sig = rpc.selector("quote(bool,int256,bytes32)")
    tokens_sig = rpc.selector("poolIdToTokens(bytes32)")
    precompile_in_sig = rpc.selector("quoteSwapExactAmountIn(address,address,uint128)")
    precompile_out_sig = rpc.selector("quoteSwapExactAmountOut(address,address,uint128)")
    print(json.dumps({"chainId": int(rpc.call("eth_chainId", []), 16), "block": latest}))
    for label, address in HOOKS.items():
        deployed = deployment_block(rpc, address, latest)
        version = decode_string(rpc.eth_call(address, version_sig, latest))
        exchange = rpc.eth_call(address, exchange_sig, latest)[-40:]
        runtime_code = bytes.fromhex(rpc.call("eth_getCode", [address, hex(latest)])[2:])
        logs = rpc.call("eth_getLogs", [{
            "fromBlock": hex(deployed),
            "toBlock": hex(min(latest, deployed + 99999)),
            "address": address,
            "topics": [registered_topic],
        }])
        print(json.dumps({
            "label": label,
            "address": address,
            "deploymentBlock": deployed,
            "version": version,
            "tempoExchange": "0x" + exchange,
            "runtimeSha256": hashlib.sha256(runtime_code).hexdigest(),
            "registeredPoolsFirst100kBlocks": [
                {"poolId": log["topics"][1], "block": int(log["blockNumber"], 16), "tx": log["transactionHash"]}
                for log in logs
            ],
        }))
        for log in logs:
            pool_id = log["topics"][1]
            token_result = rpc.eth_call(address, tokens_sig + pool_id[2:], latest)
            token0 = "0x" + token_result[26:66]
            token1 = "0x" + token_result[90:130]
            print(json.dumps({"poolId": pool_id, "token0": token0, "token1": token1}))
            for direction in (True, False):
                token_in, token_out = (token0, token1) if direction else (token1, token0)
                for exact_in in (True, False):
                    for amount in (1, 10**6, 10**9, 10**12):
                        signed = -amount if exact_in else amount
                        encoded_signed = signed % (1 << 256)
                        quote_data = (
                            quote_sig
                            + int(direction).to_bytes(32, "big").hex()
                            + encoded_signed.to_bytes(32, "big").hex()
                            + pool_id[2:]
                        )
                        precompile_data = (
                            (precompile_in_sig if exact_in else precompile_out_sig)
                            + int(token_in, 16).to_bytes(32, "big").hex()
                            + int(token_out, 16).to_bytes(32, "big").hex()
                            + amount.to_bytes(32, "big").hex()
                        )
                        row = {"poolId": pool_id, "direction": "0to1" if direction else "1to0", "type": "in" if exact_in else "out", "amount": amount}
                        for field, target, data in (("hookQuote", address, quote_data), ("exchangeQuote", "0x" + exchange, precompile_data)):
                            try:
                                row[field] = int(rpc.eth_call(target, data, latest), 16)
                            except RuntimeError as error:
                                row[field] = str(error)
                        print(json.dumps(row))


if __name__ == "__main__":
    main()
