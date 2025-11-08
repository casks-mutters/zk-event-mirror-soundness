# zk-event-mirror-soundness

## Overview
`zk-event-mirror-soundness` is a tiny CLI that verifies **cross-chain event mirroring** for a specific contract and event signature.  
It compares the number of emitted events on two EVM chains over selectable block ranges and flags **soundness mismatches**.  
This is handy for bridge contracts, message relayers, rollup inbox/outbox pairs, and zk systems like **Aztec** or **Zama**, where interface/event parity is critical.

## What it checks
1) Computes `topic0` from a Solidity event signature (e.g., `Transfer(address,address,uint256)`).  
2) Counts logs with that `topic0` for the target contract on both chains.  
3) Compares counts with an optional tolerance (`--allow-drift`).  
4) Exits non-zero on mismatch, and supports JSON output for CI dashboards.

## Installation
1) Python 3.9+  
2) Install dependency:
   pip install web3 eth-utils
3) (Optional) Set RPCs as environment variables:
   export SRC_RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY  
   export DST_RPC_URL=https://arb1.arbitrum.io/rpc

## Usage
Basic mirror check (last ~10k blocks on each chain by default):
   python app.py --address 0xYourContract --signature Transfer(address,address,uint256)

Specify explicit block ranges:
   python app.py --address 0xYourContract --signature MessageSent(bytes32,address) --src-from 19900000 --src-to 19999999 --dst-from 120000000 --dst-to 120099999

Tolerate slight drift (e.g., delayed relays):
   python app.py --address 0xYourContract --signature BridgeFinalized(bytes32,address) --allow-drift 5

Custom RPCs and tighter chunking:
   python app.py --src-rpc https://mainnet.infura.io/v3/YOUR_KEY --dst-rpc https://base-mainnet.g.alchemy.com/v2/YOUR_KEY --address 0xYourContract --signature Transfer(address,address,uint256) --step 1500

Emit JSON for CI:
   python app.py --address 0xYourContract --signature Transfer(address,address,uint256) --json

## Expected output
- Prints both chain IDs (when available), RPCs, block ranges, computed `topic0`, event counts, and drift.  
- Shows **✅ MIRROR SOUND** when `abs(src_count - dst_count) ≤ allow_drift`, else **❌ MIRROR MISMATCH**.  
- Exit codes: `0` on soundness; `2` on mismatch or fetch failures.

## Notes
- Use **stable tags** (e.g., finalized/safe equivalents per chain) by converting them to block numbers before running, if your provider supports it; this tool expects numeric ranges.  
- For proxies or upgradable systems, ensure you’re checking the **emitting** address (proxy vs implementation).  
- Provider limits vary; tune `--step` to avoid “query too large” errors.  
- In Aztec/Zama/rollup setups, event parity across chains is a key soundness invariant for bridge and inbox/outbox safety.  
- JSON output is suitable for nightly CI to detect unexpected drifts (e.g., relayer outages).  
- This tool performs **read-only** JSON-RPC calls; it never sends transactions.  
