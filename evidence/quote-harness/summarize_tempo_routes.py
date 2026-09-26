"""Summarize actual Universal Router call traces saved by tempo_multihop_replay.py."""
import json
from pathlib import Path

FILES=(
    "tempo_multihop_replay_41183156.jsonl",
    "tempo_multihop_usdce_41183156.jsonl",
    "tempo_multihop_usdce_usdt0_41115563.jsonl",
    "tempo_multihop_usdce_cusd_41115563.jsonl",
)

def walk(node):
    yield node
    for child in node.get("calls",[]): yield from walk(child)

def main():
    rows=[]
    for file in FILES:
        data=[json.loads(line) for line in Path(file).read_text().splitlines()]
        header=data[0]
        target=header["target"].lower(); payer=header["payer"].lower()
        for case in data[1:]:
            call=case["swap_then_settle"]["eth_call"]
            trace=case["swap_then_settle"].get("trace",{}).get("ok",{})
            transfers=[]
            for node in walk(trace):
                inp=node.get("input","")
                if node.get("to","").lower()==target and inp.startswith("0xa9059cbb") and ("0x"+inp[34:74]).lower()==payer:
                    transfers.append(int(inp[74:138],16))
            quote=case["quoter"].get("amountOut")
            rows.append({"file":file,"block":header["block"],"source":header["source"],"target":header["target"],"poolIds":header["poolIds"],"payer":payer,"managerInputBalance":header["poolManagerInputBalance"],"payerInputBalance":header["payerInputBalance"],"amountIn":case["amount"],"quoterOutput":quote,"execution":"success" if "ok" in call else "revert","receivedOutput":transfers[0] if len(transfers)==1 else transfers,"quoteMatchesExecution":quote==transfers[0] if len(transfers)==1 else None,"hookCalls":sum(node.get("to","").lower()==header["hook"].lower() for node in walk(trace)),"gasUsed":int(trace["gasUsed"],16) if "gasUsed" in trace else None})
    Path("tempo_real_route_summary.json").write_text(json.dumps(rows,indent=2)+"\n")
    for row in rows: print(json.dumps(row))

if __name__=="__main__":main()
