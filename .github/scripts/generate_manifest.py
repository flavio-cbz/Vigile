#!/usr/bin/env python3
"""Generate manifest.json for a Vigile Worker release."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--released-at", required=True)
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()

    dist = Path(args.dir)
    binaries = []
    for f in sorted(dist.iterdir()):
        if f.suffix in (".sha256", ".sig") or f.name == "manifest.json":
            continue
        if not f.is_file():
            continue
        sha256_file = f.with_suffix(f.suffix + ".sha256")
        sig_file = f.with_suffix(f.suffix + ".sig")
        sha256 = sha256_file.read_text().strip().split()[0] if sha256_file.exists() else ""
        sig = sig_file.read_text().strip() if sig_file.exists() else ""
        parts = f.name.split("-")  # worker-{os}-{arch}
        if len(parts) < 3:
            continue
        _, os_name, arch = parts[0], parts[1], "-".join(parts[2:])
        binaries.append(
            {
                "os": os_name,
                "arch": arch,
                "url": f"https://github.com/flavio-cbz/Vigile/releases/download/{args.version}/{f.name}",
                "sha256": sha256,
                "sig": sig,
                "size": f.stat().st_size,
            }
        )

    manifest = {
        "version": args.version,
        "released_at": args.released_at,
        "channel": "stable",
        "binaries": binaries,
    }
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Manifest written: {len(binaries)} binaries")


if __name__ == "__main__":
    main()
