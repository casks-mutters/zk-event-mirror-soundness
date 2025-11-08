# app.py
import os
import sys
import json
import time
import argparse
from typing import Dict, Tuple, List
from web3 import Web3
from eth_utils import keccak

DEFAULT_SRC = os.environ.get("SRC_RPC_URL", "https://mainnet.infura.io/v3/YOUR_INFURA_KEY")
DEFAULT_DST = os.environ.get("DST_RPC_URL", "https://arb1.arbitrum.io/rpc")

def to_checksum(addr: str) -> str:
    if not Web3.is_address(addr):
        raise ValueError(f"Invalid Ethereum address: {addr}")
    return Web3.to_checksum_address(addr)

def topic_from_signature(signature: str) -> str:
    """
    Compute keccak256(topic) from a Solidity event signature like:
    Transfer(address,address,uint256)
    """
    if "(" not in signature or ")" not in signature:
        raise ValueError("Event signature must look like Name(type1,type2,...)")
    return "0x" + keccak(text=signature).hex()

def chunk_ranges(start: int, end: int, step: int) -> List[Tuple[int, int]]:
    rngs = []
    cur = start
    while cur <= end:
        rng_end = min(cur + step - 1, end)
        rngs.append((cur, rng_end))
        cur = rng_end + 1
    return rngs

def count_logs(w3: Web3, address: str, topic0: str, from_block: int, to_block: int, step: int) -> int:
    total = 0
    for a, b in chunk_ranges(from_block, to_block, step):
        logs = w3.eth.get_logs({
            "address": to_checksum(address),
            "fromBlock": a,
            "toBlock": b,
            "topics": [topic0]
        })
        total += len(logs)
    return total

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="zk-event-mirror-soundness — cross-chain event mirror checker for bridges/agents (useful for Aztec, Zama, rollups)."
    )
    p.add_argument("--src-rpc", default=DEFAULT_SRC, help="Source chain RPC URL (default from SRC_RPC_URL)")
    p.add_argument("--dst-rpc", default=DEFAULT_DST, help="Destination chain RPC URL (default from DST_RPC_URL)")
    p.add_argument("--address", required=True, help="Contract address to inspect on both chains")
    p.add_argument("--signature", required=True, help="Event signature, e.g. Transfer(address,address,uint256)")
    p.add_argument("--src-from", type=int, help="Source chain start block (inclusive)")
    p.add_argument("--src-to", type=int, help="Source chain end block (inclusive)")
    p.add_argument("--dst-from", type=int, help="Destination chain start block (inclusive)")
    p.add_argument("--dst-to", type=int, help="Destination chain end block (inclusive)")
    p.add_argument("--step", type=int, default=2_000, help="Block chunk size per request (default: 2000)")
    p.add_argument("--timeout", type=int, default=30, help="RPC timeout seconds (default: 30)")
    p.add_argument("--json", action="store_true", help="Emit JSON summary to stdout")
    p.add_argument("--allow-drift", type=int, default=0, help="Allowed difference in counts before marking mismatch (default: 0)")
    return p.parse_args()

def main() -> None:
    start = time.time()
    args = parse_args()

    # Basic URL sanity
    for url, name in [(args.src_rpc, "source"), (args.dst_rpc, "destination")]:
        if not url.startswith(("http://", "https://")):
            print(f"❌ Invalid {name} RPC URL: {url}")
            sys.exit(1)

    # Address/Topic
    try:
        addr = to_checksum(args.address)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    try:
        topic0 = topic_from_signature(args.signature)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Providers
    w3s = Web3(Web3.HTTPProvider(args.src_rpc, request_kwargs={"timeout": args.timeout}))
    w3d = Web3(Web3.HTTPProvider(args.dst_rpc, request_kwargs={"timeout": args.timeout}))
    if not w3s.is_connected():
        print("❌ Source RPC connection failed.")
        sys.exit(1)
    if not w3d.is_connected():
        print("❌ Destination RPC connection failed.")
        sys.exit(1)

    # Figure block ranges
    src_latest = w3s.eth.block_number
    dst_latest = w3d.eth.block_number
    src_from = args.src_from if args.src_from is not None else max(0, src_latest - 10_000)
    src_to = args.src_to if args.src_to is not None else src_latest
    dst_from = args.dst_from if args.dst_from is not None else max(0, dst_latest - 10_000)
    dst_to = args.dst_to if args.dst_to is not None else dst_latest

    if src_from > src_to:
        print("❌ Invalid source range: --src-from must be <= --src-to")
        sys.exit(1)
    if dst_from > dst_to:
        print("❌ Invalid destination range: --dst-from must be <= --dst-to")
        sys.exit(1)

    print("🔧 zk-event-mirror-soundness")
    try:
        print(f"🧭 Source Chain ID: {w3s.eth.chain_id}")
    except Exception:
        pass
    try:
        print(f"🧭 Destination Chain ID: {w3d.eth.chain_id}")
    except Exception:
        pass
    print(f"🔗 Source RPC: {args.src_rpc}")
    print(f"🔗 Destination RPC: {args.dst_rpc}")
    print(f"🏷️ Contract: {addr}")
    print(f"🔑 Event topic0: {topic0}  (from '{args.signature}')")
    print(f"🧱 Source range: {src_from} → {src_to} (step={args.step})")
    print(f"🧱 Destination range: {dst_from} → {dst_to} (step={args.step})")

    # Count logs on both chains
    try:
        src_count = count_logs(w3s, addr, topic0, src_from, src_to, max(1, args.step))
    except Exception as e:
        print(f"❌ Failed to fetch source logs: {e}")
        sys.exit(2)
    try:
        dst_count = count_logs(w3d, addr, topic0, dst_from, dst_to, max(1, args.step))
    except Exception as e:
        print(f"❌ Failed to fetch destination logs: {e}")
        sys.exit(2)

    drift = abs(src_count - dst_count)
    ok = drift <= args.allow_drift

    print(f"📊 Source events: {src_count}")
    print(f"📊 Destination events: {dst_count}")
    print(f"📏 Drift: {drift} (allowed ≤ {args.allow_drift})")
       # ✅ New: Print the time when the comparison was made
    from datetime import datetime
    timestamp = datetime.utcnow().isoformat() + "Z"
    print(f"🕒 Comparison Timestamp: {timestamp}")

    if ok and src_count == dst_count:
        print("✅ MIRROR SOUND — perfect event parity detected.")
    elif ok and src_count != dst_count:
        print("🟡 MIRROR SOUND (within drift tolerance).")
    elif drift > args.allow_drift and src_count > dst_count:
        print("🔴 Mirror lagging: Destination chain missing events.")
    elif drift > args.allow_drift and src_count < dst_count:
        print("🟠 Mirror overshooting: Extra events on destination chain.")
    else:
        print("❌ MIRROR MISMATCH — unexpected event discrepancy.")
    
    elapsed = round(time.time() - start, 2)
    print(f"⏱️ Completed in {elapsed:.2f}s")

    if args.json:
        out: Dict[str, object] = {
            "contract": addr,
            "event_signature": args.signature,
            "topic0": topic0,
            "source": {
                "rpc": args.src_rpc,
                "chain_id": None,
                "from_block": src_from,
                "to_block": src_to,
                "count": src_count,
            },
            "destination": {
                "rpc": args.dst_rpc,
                "chain_id": None,
                "from_block": dst_from,
                "to_block": dst_to,
                "count": dst_count,
            },
            "drift": drift,
            "allow_drift": args.allow_drift,
            "ok": ok,
            "elapsed_seconds": elapsed,
        }
        try:
            out["source"]["chain_id"] = w3s.eth.chain_id  # type: ignore[index]
        except Exception:
            pass
        try:
            out["destination"]["chain_id"] = w3d.eth.chain_id  # type: ignore[index]
        except Exception:
            pass
        print(json.dumps(out, ensure_ascii=False, indent=2))

    sys.exit(0 if ok else 2)

if __name__ == "__main__":
    main()
