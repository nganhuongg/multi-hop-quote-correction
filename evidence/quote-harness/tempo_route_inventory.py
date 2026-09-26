"""Read-only, bounded Tempo v4 pool inventory. No transaction broadcasting."""

import argparse
import json
import sys

sys.path.insert(0, "..")
from tempo_rpc_probe import RPC

MANAGER = "0x33620f62c5b9b2086dd6b62f4a297a9f30347029"
TOKENS = {
    "PathUSD": "0x20c0000000000000000000000000000000000000",
    "B953": "0x20c000000000000000000000b9537d11c60e8b50",
    "C0520": "0x20c0000000000000000000000520792dcccccccc",
    "C14F2": "0x20c00000000000000000000014f22ca97301eb73",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://rpc.tempo.xyz")
    parser.add_argument("--start", type=int, default=41000000)
    parser.add_argument("--end", type=int, default=41274562)
    parser.add_argument("--step", type=int, default=10000)
    parser.add_argument("--token", choices=list(TOKENS), default="PathUSD")
    parser.add_argument("--position", type=int, choices=(1, 2), help="Filter one indexed currency position")
    args = parser.parse_args()
    rpc = RPC(args.rpc)
    topic = rpc.topic("Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)")
    selected = {"0x" + int(TOKENS[args.token], 16).to_bytes(32, "big").hex()}
    print(json.dumps({"chainId": int(rpc.call("eth_chainId", []), 16), "start": args.start, "end": args.end, "manager": MANAGER, "tokens": TOKENS}), flush=True)
    for start in range(args.start, args.end + 1, args.step):
        end = min(args.end, start + args.step - 1)
        for token_topic in selected:
            for position in ((args.position,) if args.position else (1, 2)):
                topics = [topic, token_topic] if position == 1 else [topic, None, token_topic]
                logs = rpc.call("eth_getLogs", [{"fromBlock": hex(start), "toBlock": hex(end), "address": MANAGER, "topics": topics}])
                for log in logs:
                    words = [log["data"][2+i*64:2+(i+1)*64] for i in range(5)]
                    print(json.dumps({"block": int(log["blockNumber"], 16), "tx": log["transactionHash"], "poolId": log["topics"][1], "token0": "0x"+log["topics"][2][-40:], "token1": "0x"+log["topics"][3][-40:], "fee": int(words[0],16), "tickSpacing": int(words[1],16), "hook": "0x"+words[2][-40:], "sqrtPriceX96": int(words[3],16), "tick": int(words[4],16)}), flush=True)


if __name__ == "__main__":
    main()
