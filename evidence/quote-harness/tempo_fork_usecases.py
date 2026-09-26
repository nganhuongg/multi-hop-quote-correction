"""Reproduce the cUSD balance threshold on a local Tempo Anvil fork.

Start Anvil at block 41183156 first. This script changes ONLY the test payer's
cUSD balance via anvil_dealTIP20 and restores its snapshot when done. It never
funds PoolManager or Tempo Exchange and never broadcasts to Tempo mainnet.
"""

import argparse
import json

from tempo_multihop_replay import (
    CUSD, HOOK, MANAGER, PAYER, PATHUSD, QUOTER, ROUTER, USDT0,
    P_CUSD, P_USDT0, balance, call, quote_data, route_data,
)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tempo_rpc_probe import RPC


def hook_quote(rpc, pool_id, zero_for_one, amount, block):
    selector=rpc.selector("quote(bool,int256,bytes32)")
    data=selector+int(zero_for_one).to_bytes(32,"big").hex()+((-amount)%(1<<256)).to_bytes(32,"big").hex()+pool_id[2:]
    out=call(rpc,"eth_call",[{"to":HOOK,"data":data},block])
    return int(out["ok"],16) if "ok" in out else out


def output_to_payer(trace):
    transfers=[]
    def walk(node):
        txdata=node.get("input","")
        if node.get("to","").lower()==USDT0 and txdata.startswith("0xa9059cbb"):
            recipient="0x"+txdata[34:74]
            if recipient.lower()==PAYER:
                transfers.append(int(txdata[74:138],16))
        for child in node.get("calls",[]): walk(child)
    walk(trace)
    return transfers


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rpc",default="http://127.0.0.1:8546")
    parser.add_argument("--trace-file",default="tempo_fork_trace_25m.json")
    args=parser.parse_args()
    rpc=RPC(args.rpc)
    block=int(rpc.call("eth_blockNumber",[]),16)
    assert block==41183156, f"expected pinned Anvil fork 41183156, got {block}"
    snapshot=rpc.call("evm_snapshot",[])
    try:
        before={"managerCUSD":balance(rpc,CUSD,MANAGER,block),"payerCUSD":balance(rpc,CUSD,PAYER,block)}
        print(json.dumps({"case":"setup","chainId":int(rpc.call("eth_chainId",[]),16),"block":block,"payer":PAYER,"poolManager":MANAGER,"hook":HOOK,"quoter":QUOTER,"router":ROUTER,"poolIds":[P_CUSD,P_USDT0],"before":before,"walletOverride":"anvil_dealTIP20 payer cUSD = 30000000; no PM/DEX override"}),flush=True)
        rpc.call("anvil_dealTIP20",[PAYER,CUSD,hex(30000000)])
        assert balance(rpc,CUSD,MANAGER,block)==before["managerCUSD"]
        for amount in (1000000,19000000,19862459,19862460,20000000,25000000):
            b=hex(block)
            first=hook_quote(rpc,P_CUSD,False,amount,b)
            second=hook_quote(rpc,P_USDT0,True,first,b) if isinstance(first,int) else None
            q=call(rpc,"eth_call",[{"from":PAYER,"to":QUOTER,"data":quote_data(amount)},b])
            standard={"from":PAYER,"to":ROUTER,"data":route_data(amount,False),"value":"0x0"}
            prepay={"from":PAYER,"to":ROUTER,"data":route_data(amount,True),"value":"0x0"}
            standard_call=call(rpc,"eth_call",[standard,b])
            prepay_call=call(rpc,"eth_call",[prepay,b])
            trace=call(rpc,"debug_traceCall",[prepay,b,{"tracer":"callTracer","tracerConfig":{"withLog":True}}])
            trace_obj=trace.get("ok",{})
            if amount==25000000:
                with open(args.trace_file,"w") as out: json.dump({"prepay":trace,"standard":call(rpc,"debug_traceCall",[standard,b,{"tracer":"callTracer","tracerConfig":{"withLog":True}}]),"quoter":call(rpc,"debug_traceCall",[{"from":PAYER,"to":QUOTER,"data":quote_data(amount)},b,{"tracer":"callTracer"}])},out)
            row={"case":"amount","amountIn":amount,"managerCUSD":balance(rpc,CUSD,MANAGER,block),"payerCUSD":balance(rpc,CUSD,PAYER,block),"directHookFirst":first,"directHookSecond":second,"v4Quoter":int(q["ok"][2:66],16) if "ok" in q else "revert","v4QuoterError":q.get("error"),"universalRouterSwapThenSettle":"success" if "ok" in standard_call else "revert","standardError":standard_call.get("error"),"universalRouterSettleThenSwap":"success" if "ok" in prepay_call else "revert","prepayError":prepay_call.get("error"),"receivedUSDT0":output_to_payer(trace_obj) if "ok" in trace else [],"gasUsed":int(trace_obj.get("gasUsed","0x0"),16) if "ok" in trace else None,"traceError":trace.get("error")}
            print(json.dumps(row),flush=True)
        rpc.call("anvil_dealTIP20",[PAYER,CUSD,hex(1000000000000)])
        amount=1000000000000; b=hex(block)
        first=hook_quote(rpc,P_CUSD,False,amount,b)
        prepay={"from":PAYER,"to":ROUTER,"data":route_data(amount,True),"value":"0x0"}
        execution=call(rpc,"eth_call",[prepay,b])
        illiquid_trace=call(rpc,"debug_traceCall",[prepay,b,{"tracer":"callTracer"}])
        with open(args.trace_file.replace("25m","illiquid"),"w") as out: json.dump(illiquid_trace,out)
        print(json.dumps({"case":"insufficient_external_liquidity","amountIn":amount,"directHookFirst":first,"universalRouterSettleThenSwap":"success" if "ok" in execution else "revert","executionError":execution.get("error"),"managerCUSD":balance(rpc,CUSD,MANAGER,block),"payerCUSD":balance(rpc,CUSD,PAYER,block),"walletOverride":"anvil_dealTIP20 payer cUSD = 1000000000000; no PM/DEX override"}),flush=True)
    finally:
        rpc.call("evm_revert",[snapshot])


if __name__=="__main__": main()
