"""Pinned-block read-only quotes and balances for discovered Tempo pools."""

import argparse
import json
import subprocess
import sys

sys.path.insert(0, "..")
from tempo_rpc_probe import RPC, decode_string

MANAGER = "0x33620f62c5b9b2086dd6b62f4a297a9f30347029"
QUOTER = "0x20e6487c371a2086f841ef453f85378223df4f4e"
HOOK = "0x7169a78a59f136876e724b648fbb339a42f46888"
ZERO = "0x" + "0" * 40
P = "0x20c0000000000000000000000000000000000000"
POOLS = [
    ("agg_B953", P, "0x20c000000000000000000000b9537d11c60e8b50", 500, 10, HOOK, "0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588"),
    ("agg_C0520", P, "0x20c0000000000000000000000520792dcccccccc", 500, 10, HOOK, "0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57"),
    ("agg_C14F2", P, "0x20c00000000000000000000014f22ca97301eb73", 500, 10, HOOK, "0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22"),
    ("v4_B953", P, "0x20c000000000000000000000b9537d11c60e8b50", 2500, 25, ZERO, "0xce0d1c0b87a8b1a92cd0865013c2bd9440be49fdf7a3d3514e82f02352a4e2dd"),
    ("v4_C412", P, "0x20c000000000000000000000c412ec89d0c08be5", 3000, 10, ZERO, "0x51d5133ef1f7317b98228f02f49a5a828035f2c2081584c553db622faa4c6830"),
]


def calldata(signature, argument):
    return subprocess.check_output(["/Users/harry/.foundry/bin/cast", "calldata", signature, argument], text=True).strip()


def result_or_error(rpc, request, block):
    try:
        return rpc.call("eth_call", [request, hex(block)])
    except Exception as error:
        return {"error": str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://rpc.tempo.xyz")
    parser.add_argument("--block", type=int, default=41274562)
    args = parser.parse_args()
    rpc = RPC(args.rpc)
    print(json.dumps({"chainId": int(rpc.call("eth_chainId", []), 16), "block": args.block, "poolManager": MANAGER, "quoter": QUOTER}), flush=True)
    for token in sorted({pool[1] for pool in POOLS} | {pool[2] for pool in POOLS}):
        balance = result_or_error(rpc, {"to": token, "data": rpc.selector("balanceOf(address)") + int(MANAGER,16).to_bytes(32,"big").hex()}, args.block)
        decimals = result_or_error(rpc, {"to": token, "data": rpc.selector("decimals()")}, args.block)
        symbol = result_or_error(rpc, {"to": token, "data": rpc.selector("symbol()")}, args.block)
        print(json.dumps({"token": token, "managerBalance": int(balance,16) if isinstance(balance,str) else balance, "decimals": int(decimals,16) if isinstance(decimals,str) else decimals, "symbol": decode_string(symbol) if isinstance(symbol,str) else symbol}), flush=True)
    sig = "quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))"
    for label, token0, token1, fee, spacing, hook, pool_id in POOLS:
        for direction in (True, False):
            for amount in (100000, 1000000, 10000000, 100000000, 1000000000):
                arg = f"(({token0},{token1},{fee},{spacing},{hook}),{str(direction).lower()},{amount},0x)"
                data = calldata(sig, arg)
                result = result_or_error(rpc, {"to": QUOTER, "data": data}, args.block)
                quote = [int(result[2:66],16), int(result[66:130],16)] if isinstance(result,str) and len(result)>=130 else result
                print(json.dumps({"pool": label, "poolId": pool_id, "direction": "0to1" if direction else "1to0", "amountIn": amount, "quoter": quote}), flush=True)


if __name__ == "__main__":
    main()
