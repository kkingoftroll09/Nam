"""
New Token Scanner
=================

This single-file script implements the Assignment 1 — "New Token Scanner" for EVM chains (ETH/BSC).
It listens for new blocks, detects contract creations, tries to read ERC-20 metadata (name, symbol, decimals, totalSupply), checks for Transfer logs, stores results in a SQLite DB, avoids duplicates, and waits >= confirmations before publishing a discovered token.

This version includes robust import fallbacks and an optional --run-duration flag for timed smoke tests.
"""

import argparse
import os
import sys
import time
import json
import csv
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Any

# Optional imports: allow the script to run even if some optional packages
# aren't present; we import lazily and provide fallbacks where useful.
try:
    from web3 import Web3
    from web3.exceptions import BadFunctionCallOutput, ContractLogicError
    from web3._utils.events import get_event_data
except Exception:
    Web3 = None
    BadFunctionCallOutput = Exception
    ContractLogicError = Exception
    get_event_data = None

# Minimal ERC-20 ABI fragments
ERC20_MIN_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]

# Compute Transfer event topic. Prefer Web3.keccak; fall back to eth_utils.keccak if available.
# As a last resort use the known constant for the Transfer event topic.
try:
    TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()
except Exception:
    try:
        from eth_utils import keccak as _keccak

        try:
            TRANSFER_EVENT_SIG = _keccak(text="Transfer(address,address,uint256)").hex()
        except TypeError:
            TRANSFER_EVENT_SIG = _keccak(b"Transfer(address,address,uint256)").hex()
    except Exception:
        TRANSFER_EVENT_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Normalize to ensure a 0x-prefixed hex string for web3 get_logs topics
try:
    if not TRANSFER_EVENT_SIG.startswith("0x"):
        TRANSFER_EVENT_SIG = "0x" + TRANSFER_EVENT_SIG.lstrip("0x")
except Exception:
    # keep whatever value; downstream code will handle errors
    pass

DEFAULT_POLL = 4  # seconds between polls (not the confirmation wait)


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            chain TEXT,
            address TEXT UNIQUE,
            creation_block INTEGER,
            found_block INTEGER,
            tx_hash TEXT,
            timestamp_utc TEXT,
            name TEXT,
            symbol TEXT,
            decimals INTEGER,
            total_supply TEXT,
            has_transfer_logs INTEGER,
            extra_json TEXT
        )
        """
    )
    conn.commit()
    return conn


def safe_contract_call(w3: Any, address: str, fn_name: str, abi_fragment: dict, block_identifier: Optional[int] = None, timeout_seconds: int = 10):
    """Attempt a low-risk eth_call for the given function name. Returns (success, value_or_error)"""
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=[abi_fragment])
        func = getattr(contract.functions, fn_name)()
        val = func.call(block_identifier=block_identifier)
        return True, val
    except (BadFunctionCallOutput, ContractLogicError, ValueError) as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def export_csv_json(conn: sqlite3.Connection, csv_path: str, json_path: str):
    c = conn.cursor()
    c.execute("SELECT chain,address,creation_block,found_block,tx_hash,timestamp_utc,name,symbol,decimals,total_supply,has_transfer_logs,extra_json FROM tokens ORDER BY id")
    rows = c.fetchall()
    headers = [x[0] for x in c.description]

    with open(csv_path, "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)

    out = []
    for r in rows:
        out.append(dict(zip(headers, r)))
    with open(json_path, "w", encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(rows)} discoveries to {csv_path} and {json_path}")


def already_seen(conn: sqlite3.Connection, address: str) -> bool:
    c = conn.cursor()
    c.execute("SELECT 1 FROM tokens WHERE address = ?", (address.lower(),))
    return c.fetchone() is not None


def save_token(conn: sqlite3.Connection, data: dict):
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO tokens (chain,address,creation_block,found_block,tx_hash,timestamp_utc,name,symbol,decimals,total_supply,has_transfer_logs,extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("chain"),
            data.get("address").lower(),
            data.get("creation_block"),
            data.get("found_block"),
            data.get("tx_hash"),
            data.get("timestamp_utc"),
            data.get("name"),
            data.get("symbol"),
            data.get("decimals"),
            data.get("total_supply"),
            1 if data.get("has_transfer_logs") else 0,
            json.dumps(data.get("extra_json", {})),
        ),
    )
    conn.commit()


def inspect_contract(w3: Any, address: str, creation_block: int, found_block: int):
    info = {
        "name": None,
        "symbol": None,
        "decimals": None,
        "total_supply": None,
        "has_transfer_logs": False,
        "extra_json": {},
    }

    ok, val = safe_contract_call(w3, address, "name", ERC20_MIN_ABI[0], block_identifier=found_block)
    if ok:
        try:
            info["name"] = val
        except Exception:
            info["extra_json"]["name_call_raw"] = str(val)

    ok, val = safe_contract_call(w3, address, "symbol", ERC20_MIN_ABI[1], block_identifier=found_block)
    if ok:
        try:
            info["symbol"] = val
        except Exception:
            info["extra_json"]["symbol_call_raw"] = str(val)

    ok, val = safe_contract_call(w3, address, "decimals", ERC20_MIN_ABI[2], block_identifier=found_block)
    if ok:
        try:
            info["decimals"] = int(val)
        except Exception:
            info["extra_json"]["decimals_call_raw"] = str(val)

    ok, val = safe_contract_call(w3, address, "totalSupply", ERC20_MIN_ABI[3], block_identifier=found_block)
    if ok:
        try:
            info["total_supply"] = str(val)
        except Exception:
            info["extra_json"]["total_supply_call_raw"] = str(val)

    try:
        from_block = creation_block
        to_block = found_block
        logs = w3.eth.get_logs({"fromBlock": from_block, "toBlock": to_block, "address": Web3.to_checksum_address(address), "topics": [TRANSFER_EVENT_SIG]})
        info["has_transfer_logs"] = len(logs) > 0
        info["extra_json"]["transfer_log_count"] = len(logs)
    except Exception as e:
        info["extra_json"]["transfer_log_error"] = str(e)

    return info


def main_loop(w3: Any, conn: sqlite3.Connection, args):
    last_processed_block = args.start_block if args.start_block is not None else None
    print("Starting main loop. Waiting for new blocks...")
    start_time = time.time()

    while True:
        try:
            latest = w3.eth.block_number
        except Exception as e:
            print("Error fetching latest block:", e)
            time.sleep(max(5, args.poll_interval))
            continue

        if last_processed_block is None:
            last_processed_block = latest - 1

        if latest <= last_processed_block:
            time.sleep(args.poll_interval)
            continue

        target_block = latest - args.confirmations + 1
        if target_block <= last_processed_block:
            time.sleep(args.poll_interval)
            continue

        for blk in range(last_processed_block + 1, target_block + 1):
            try:
                block = w3.eth.get_block(blk, full_transactions=True)
            except Exception as e:
                print(f"Failed to fetch block {blk}: {e}")
                continue

            print(f"Scanning block {blk} ({len(block.transactions)} txs)")

            for tx in block.transactions:
                try:
                    to_addr = tx.to
                except Exception:
                    to_addr = None

                if to_addr is None:
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx.hash)
                    except Exception as e:
                        print(f"  Could not get receipt for tx {tx.hash.hex()}: {e}")
                        continue

                    # web3 versions differ in attribute naming: some expose receipt.contract_address,
                    # others use contractAddress in the dict-like receipt. Support both.
                    contract_address = None
                    try:
                        # Attribute access (web3 v5 style)
                        contract_address = getattr(receipt, "contract_address", None)
                    except Exception:
                        contract_address = None
                    if not contract_address:
                        # dict-like access (web3 v6 style)
                        try:
                            if hasattr(receipt, "get"):
                                contract_address = receipt.get("contractAddress")
                        except Exception:
                            contract_address = None
                    if not contract_address:
                        continue

                    checksum_addr = Web3.to_checksum_address(contract_address)
                    print(f"  Detected contract creation: {checksum_addr} in tx {tx.hash.hex()} block {blk}")

                    if already_seen(conn, checksum_addr):
                        print("    Already recorded. Skipping.")
                        continue

                    found_block = latest
                    timestamp_utc = datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat()

                    info = inspect_contract(w3, checksum_addr, creation_block=blk, found_block=blk)
                    if getattr(args, "verbose", False):
                        print(f"    Inspection info for {checksum_addr}: {json.dumps(info, ensure_ascii=False)}")

                    # Append to debug log if requested
                    if getattr(args, "debug_log", None):
                        try:
                            entry = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "chain": args.chain,
                                "address": checksum_addr,
                                "creation_block": blk,
                                "found_block": target_block,
                                "tx_hash": tx.hash.hex(),
                                "inspection": info,
                            }
                            with open(args.debug_log, "a", encoding="utf-8") as df:
                                df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        except Exception as e:
                            print(f"    Failed to write debug log: {e}")

                    data = {
                        "chain": args.chain,
                        "address": checksum_addr,
                        "creation_block": blk,
                        "found_block": target_block,
                        "tx_hash": tx.hash.hex(),
                        "timestamp_utc": timestamp_utc,
                        "name": info.get("name"),
                        "symbol": info.get("symbol"),
                        "decimals": info.get("decimals"),
                        "total_supply": info.get("total_supply"),
                        "has_transfer_logs": info.get("has_transfer_logs"),
                        "extra_json": info.get("extra_json"),
                    }

                    plausible = any([
                        data["name"],
                        data["symbol"],
                        data["decimals"] is not None,
                        data["has_transfer_logs"],
                    ])

                    # Save if plausible OR if user requested saving all candidates
                    if plausible or getattr(args, "save_all", False):
                        save_token(conn, data)
                        if plausible:
                            print(f"    Saved token {checksum_addr} (name={data['name']} symbol={data['symbol']} decimals={data['decimals']})")
                        else:
                            print(f"    Saved contract {checksum_addr} (no ERC-20 metadata detected)")

                        # If user requested, stop when DB reaches a certain number of tokens
                        try:
                            if getattr(args, "stop_at_count", 0) > 0:
                                cur = conn.cursor()
                                cur.execute("SELECT COUNT(1) FROM tokens")
                                cnt = cur.fetchone()[0]
                                if cnt >= args.stop_at_count:
                                    print(f"Reached stop-at-count ({cnt} >= {args.stop_at_count}). Exiting main loop.")
                                    export_csv_json(conn, args.csv_output, args.json_output)
                                    return
                        except Exception as e:
                            print(f"    Error checking stop_at_count: {e}")

            last_processed_block = blk

        export_csv_json(conn, args.csv_output, args.json_output)

        if getattr(args, "run_duration", 0) and (time.time() - start_time) >= args.run_duration:
            print(f"Reached run duration ({args.run_duration}s). Exported DB and exiting.")
            return

        time.sleep(args.poll_interval)


def parse_args():
    p = argparse.ArgumentParser(description="New Token Scanner for EVM (ETH/BSC)")
    p.add_argument("--rpc", type=str, default=os.environ.get("RPC_URL"), help="RPC URL (or set RPC_URL env var)")
    p.add_argument("--chain", type=str, default="eth", choices=["eth", "bsc"], help="chain label for storage")
    p.add_argument("--start-block", type=int, default=None, help="start scanning from this block")
    p.add_argument("--db", type=str, default="tokens.db", help="SQLite DB path")
    p.add_argument("--confirmations", type=int, default=3, help="number of confirmations to wait before publishing")
    p.add_argument("--poll-interval", type=int, default=DEFAULT_POLL, help="seconds between new-block polls")
    p.add_argument("--csv-output", type=str, default="discovered_tokens.csv", help="CSV output path")
    p.add_argument("--json-output", type=str, default="discovered_tokens.json", help="JSON output path")
    p.add_argument("--run-duration", type=int, default=0, help="Seconds to run before exiting (0 = run forever)")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging for inspected contracts")
    p.add_argument("--debug-log", type=str, default=None, help="Path to append JSONL debug log of all inspected contract candidates")
    p.add_argument("--save-all", action="store_true", help="Save every detected contract candidate to the DB, even if not plausible ERC-20")
    p.add_argument("--stop-at-count", type=int, default=0, help="Stop scanning and exit when the DB contains at least this many tokens (0 = disabled)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.rpc:
        print("Error: RPC URL not provided. Set --rpc or RPC_URL env var.")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30})) if Web3 is not None else None
    if w3 is None or not w3.is_connected():
        print("Failed to connect to RPC at", args.rpc)
        sys.exit(1)

    conn = init_db(args.db)

    try:
        main_loop(w3, conn, args)
    except KeyboardInterrupt:
        print("Interrupted. Exporting DB to CSV/JSON before exit...")
        export_csv_json(conn, args.csv_output, args.json_output)
        print("Bye")
