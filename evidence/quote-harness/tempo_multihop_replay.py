"""Read-only V4Quoter/UniversalRouter calls on real Tempo state.

Uses a historical cUSD payer whose actual Universal Router swap succeeded.
No account, PoolManager or DEX state overrides and no transaction broadcast.
"""

import argparse
import json
import subprocess
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tempo_rpc_probe import RPC, abi_bytes_array, word

QUOTER = "0x20e6487c371a2086f841ef453f85378223df4f4e"
ROUTER = "0x182a927119d56008d921126764bf884221b10f59"
HOOK = "0x7169a78a59f136876e724b648fbb339a42f46888"
PAYER = "0xf9efc19218e6a9e58df5767ffa627f37de2bf7cc"
MANAGER = "0x33620f62c5b9b2086dd6b62f4a297a9f30347029"
CUSD = "0x20c0000000000000000000000520792dcccccccc"
PATHUSD = "0x20c0000000000000000000000000000000000000"
USDT0 = "0x20c00000000000000000000014f22ca97301eb73"
USDCE = "0x20c000000000000000000000b9537d11c60e8b50"
P_CUSD = "0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57"
P_USDT0 = "0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22"
P_USDCE = "0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588"


def cast(mode, sig, *args):
    return subprocess.check_output([shutil.which("cast") or str(Path.home() / ".foundry/bin/cast"), mode, sig, *args], text=True).strip()


def route_data(amount, settle_first=False, target=USDT0, source=CUSD, payer=PAYER, permit_input=None, deadline=None):
    path = f"[( {PATHUSD},500,10,{HOOK},0x),( {target},500,10,{HOOK},0x)]".replace(" ", "")
    swap = cast("abi-encode", "f((address,(address,uint24,int24,address,bytes)[],uint256[],uint128,uint128))", f"({source},{path},[],{amount},0)")
    # Action 0x0b = SETTLE(currency, amount, payerIsUser). 0 means OPEN_DELTA
    # only in the usual post-swap action; prepayment uses the explicit amount.
    settle = cast("abi-encode", "f(address,uint256,bool)", source, str(amount if settle_first else 0), "true")
    take = cast("abi-encode", "f(address,address,uint256)", target, payer, "0")
    actions = "0x0b070e" if settle_first else "0x070b0e"
    params = [settle, swap, take] if settle_first else [swap, settle, take]
    v4 = cast("abi-encode", "f(bytes,bytes[])", actions, "[" + ",".join(params) + "]")
    if permit_input is not None:
        return cast("calldata", "execute(bytes,bytes[],uint256)", "0x0a10", "["+permit_input+","+v4+"]", str(deadline))
    return cast("calldata", "execute(bytes,bytes[])", "0x10", "[" + v4 + "]")


def quote_data(amount, target=USDT0, source=CUSD):
    path = f"[({PATHUSD},500,10,{HOOK},0x),({target},500,10,{HOOK},0x)]"
    return cast("calldata", "quoteExactInput((address,(address,uint24,int24,address,bytes)[],uint128))", f"({source},{path},{amount})")


def call(rpc, method, params):
    try:
        return {"ok": rpc.call(method, params)}
    except Exception as error:
        return {"error": str(error)}


def balance(rpc, token, owner, block):
    data = rpc.selector("balanceOf(address)") + int(owner,16).to_bytes(32,"big").hex()
    out = call(rpc,"eth_call",[{"to":token,"data":data},hex(block)])
    return int(out["ok"],16) if "ok" in out else out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://rpc.tempo.xyz")
    parser.add_argument("--block", type=int, default=41183156)
    parser.add_argument("--amount", type=int, action="append")
    parser.add_argument("--target", choices=("usdt0","usdce","cusd"), default="usdt0")
    parser.add_argument("--source", choices=("cusd","usdce","usdt0"), default="cusd")
    parser.add_argument("--payer", default=PAYER)
    parser.add_argument("--permit-template-tx", help="Reuse the original Permit2 permit command from a historical transaction")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    rpc = RPC(args.rpc)
    target = {"usdt0":USDT0,"usdce":USDCE,"cusd":CUSD}[args.target]
    target_pool = {"usdt0":P_USDT0,"usdce":P_USDCE,"cusd":P_CUSD}[args.target]
    source = {"cusd":CUSD,"usdce":USDCE,"usdt0":USDT0}[args.source]
    source_pool = {"cusd":P_CUSD,"usdce":P_USDCE,"usdt0":P_USDT0}[args.source]
    permit_input = deadline = None
    if args.permit_template_tx:
        template=rpc.call("eth_getTransactionByHash",[args.permit_template_tx])
        assert template["from"].lower()==args.payer.lower()
        raw=bytes.fromhex(template["input"][10:])
        inputs=abi_bytes_array(raw,word(raw,32))
        permit_input="0x"+inputs[0].hex()
        deadline=word(raw,64)
    block = hex(args.block)
    amounts = args.amount or [1000000, 5249475, 10000000, 20000000, 25000000]
    print(json.dumps({"block":args.block,"chainId":int(rpc.call("eth_chainId",[]),16),"payer":args.payer,"router":ROUTER,"quoter":QUOTER,"hook":HOOK,"source":source,"target":target,"poolIds":[source_pool,target_pool],"poolManagerInputBalance":balance(rpc,source,MANAGER,args.block),"payerInputBalance":balance(rpc,source,args.payer,args.block),"scriptAppliesStateOverrides":False}),flush=True)
    for amount in amounts:
        q = call(rpc,"eth_call",[{"from":args.payer,"to":QUOTER,"data":quote_data(amount,target,source)},block])
        if "ok" in q:
            raw=q["ok"]; q={"amountOut":int(raw[2:66],16),"gasEstimate":int(raw[66:130],16)}
        row={"amount":amount,"quoter":q}
        for label, settle_first in (("swap_then_settle",False),("settle_then_swap",True)):
            tx={"from":args.payer,"to":ROUTER,"data":route_data(amount,settle_first,target,source,args.payer,permit_input,deadline),"value":"0x0"}
            row[label]={"eth_call":call(rpc,"eth_call",[tx,block]),"estimateGas":call(rpc,"eth_estimateGas",[tx,block])}
            if args.trace:
                row[label]["trace"] = call(rpc,"debug_traceCall",[tx,block,{"tracer":"callTracer","tracerConfig":{"withLog":True}}])
        print(json.dumps(row),flush=True)


if __name__=="__main__":
    main()
