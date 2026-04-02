#!/usr/bin/env python3
"""Clean up stopped OpenSandbox containers to free disk space."""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPEN_SANDBOX_API_KEY", "")
DOMAIN = os.getenv("OPEN_SANDBOX_DOMAIN", "localhost:8080")
BASE_URL = f"http://{DOMAIN}" if not DOMAIN.startswith("http") else DOMAIN


def main():
    headers = {"OPEN-SANDBOX-API-KEY": API_KEY}

    print("Fetching sandbox list...")
    resp = httpx.get(f"{BASE_URL}/v1/sandboxes", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    sandboxes = data.get("items", [])

    if not sandboxes:
        print("No sandboxes found.")
        return

    print(f"\nFound {len(sandboxes)} total sandboxes:")
    print("-" * 80)

    stopped = []
    active = []

    for s in sandboxes:
        sid = s.get("id", "?")
        state = s.get("state", "UNKNOWN")
        metadata = s.get("metadata", {})
        thread_id = metadata.get("thread_id", "no-thread-id")[:12]

        info = f"ID: {sid[:12]}... | State: {state:15} | Thread: {thread_id}"

        if state in ("stopped", "error", "exited"):
            stopped.append((sid, info))
            print(f"  [DELETE] {info}")
        else:
            active.append((sid, info))
            print(f"  [KEEP]   {info}")

    print("-" * 80)
    print(f"\nSummary:")
    print(f"  Active:  {len(active)}")
    print(f"  Stopped: {len(stopped)}")

    if not stopped:
        print("\n✅ No stopped sandboxes to clean up.")
        return

    print(f"\n⚠️  Will delete {len(stopped)} stopped sandbox(es).")

    auto_confirm = "--yes" in sys.argv or "-y" in sys.argv
    if auto_confirm:
        print("Auto-confirming (--yes flag)")
        confirm = "y"
    else:
        confirm = input("Proceed? [y/N]: ").strip().lower()

    if confirm != "y":
        print("Cancelled.")
        return

    print("\nDeleting stopped sandboxes...")
    deleted = 0
    failed = 0

    for sid, info in stopped:
        try:
            r = httpx.delete(f"{BASE_URL}/v1/sandboxes/{sid}", headers=headers, timeout=30)
            r.raise_for_status()
            print(f"  ✅ Deleted: {sid[:12]}...")
            deleted += 1
        except Exception as e:
            print(f"  ❌ Failed: {sid[:12]}... - {e}")
            failed += 1

    print("-" * 80)
    print(f"✅ Cleanup complete: {deleted} deleted, {failed} failed")


if __name__ == "__main__":
    main()
