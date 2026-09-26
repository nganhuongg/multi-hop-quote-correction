"""Bounded read-only scan of one verified aggregator pool's swap events."""
import argparse
import json
import sys
sys.path.insert(0,"..")
from tempo_rpc_probe import RPC

HOOK="0x7169a78a59f136876e724b648fbb339a42f46888"
POOL="0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",type=int,default=41000000)
    p.add_argument("--end",type=int,default=41274562)
    p.add_argument("--rpc",default="https://rpc.tempo.xyz")
    p.add_argument("--pool",default=POOL)
    a=p.parse_args(); r=RPC(a.rpc)
    topic=r.topic("HookSwap(bytes32,address,int256,int256,uint24)")
    print(json.dumps({"chainId":int(r.call("eth_chainId",[]),16),"start":a.start,"end":a.end,"hook":HOOK,"poolId":a.pool}),flush=True)
    for lo in range(a.start,a.end+1,100000):
        hi=min(lo+99999,a.end)
        logs=r.call("eth_getLogs",[{"fromBlock":hex(lo),"toBlock":hex(hi),"address":HOOK,"topics":[topic,a.pool]}])
        for x in logs:
            d=x["data"][2:]
            # indexed poolId, sender; data begins amount0, amount1, fee
            amount0=int.from_bytes(bytes.fromhex(d[:64]),"big",signed=True)
            amount1=int.from_bytes(bytes.fromhex(d[64:128]),"big",signed=True)
            print(json.dumps({"block":int(x["blockNumber"],16),"tx":x["transactionHash"],"amount0":amount0,"amount1":amount1}),flush=True)

if __name__=="__main__": main()
