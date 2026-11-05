#!/usr/bin/env python3
"""Generate machine-local TLS files using an already installed mkcert."""
import argparse
import ipaddress
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Mac LAN IPv4 address")
    args = parser.parse_args()
    try:
        host = str(ipaddress.IPv4Address(args.host))
    except ipaddress.AddressValueError:
        parser.error("--host must be the Mac's LAN IPv4 address")
    mkcert = shutil.which("mkcert")
    if not mkcert:
        parser.error("Install mkcert first: brew install mkcert; then run mkcert -install")
    root = Path(__file__).resolve().parents[1]
    certs = root / "certs"
    certs.mkdir(mode=0o700, exist_ok=True)
    subprocess.run([mkcert, "-cert-file", str(certs / "localhost.pem"),
                    "-key-file", str(certs / "localhost-key.pem"),
                    "localhost", "127.0.0.1", "::1", host], check=True)
    (certs / "localhost-key.pem").chmod(0o600)
    print("Certificates generated in ignored certs/. Trust the mkcert CA on each device; see docs/setup.md.")
    print(f"Start with: export VR_HOST_IP={host}")


if __name__ == "__main__":
    main()
