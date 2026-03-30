#!/usr/bin/env python3
"""Clean up stopped Daytona sandboxes to free disk space."""

import sys
from daytona import Daytona, SandboxState

def main():
    d = Daytona()

    print("Fetching sandbox list...")
    result = d.list()
    sandboxes = result.items if hasattr(result, 'items') else list(result)

    if not sandboxes:
        print("No sandboxes found.")
        return

    print(f"\nFound {len(sandboxes)} total sandboxes:")
    print("-" * 80)

    stopped = []
    active = []

    for s in sandboxes:
        state = getattr(s, 'state', 'UNKNOWN')
        labels = getattr(s, 'labels', {})
        thread_id = labels.get('thread_id', 'no-thread-id')[:12]

        info = f"ID: {s.id[:12]}... | State: {state:15} | Thread: {thread_id}"

        if state in (SandboxState.STOPPED, SandboxState.ARCHIVED,
                     SandboxState.ERROR, SandboxState.BUILD_FAILED):
            stopped.append((s, info))
            print(f"  [DELETE] {info}")
        else:
            active.append((s, info))
            print(f"  [KEEP]   {info}")

    print("-" * 80)
    print(f"\nSummary:")
    print(f"  Active:  {len(active)}")
    print(f"  Stopped: {len(stopped)}")

    if not stopped:
        print("\n✅ No stopped sandboxes to clean up.")
        return

    print(f"\n⚠️  Will delete {len(stopped)} stopped sandbox(es).")

    # Check for --yes flag
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv

    if auto_confirm:
        print("Auto-confirming (--yes flag)")
        confirm = 'y'
    else:
        confirm = input("Proceed? [y/N]: ").strip().lower()

    if confirm != 'y':
        print("Cancelled.")
        return

    print("\nDeleting stopped sandboxes...")
    deleted = 0
    failed = 0

    for s, info in stopped:
        try:
            d.delete(s)
            print(f"  ✅ Deleted: {s.id[:12]}...")
            deleted += 1
        except Exception as e:
            print(f"  ❌ Failed: {s.id[:12]}... - {e}")
            failed += 1

    print("-" * 80)
    print(f"✅ Cleanup complete: {deleted} deleted, {failed} failed")
    print("You can now create new sandboxes.")

if __name__ == "__main__":
    main()
