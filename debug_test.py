#!/usr/bin/env python3

print("=== DEBUG SCRIPT START ===")

try:
    print("1. Testing basic imports...")
    import sys
    print(f"   Python version: {sys.version}")

    import argparse
    print("   argparse: OK")

    import time
    print("   time: OK")

    import socket
    print("   socket: OK")

    import requests
    print("   requests: OK")

    from threading import Thread, Event
    print("   threading: OK")

    from queue import Queue
    print("   queue: OK")

    import urllib3
    print("   urllib3: OK")

    from requests.adapters import HTTPAdapter
    print("   HTTPAdapter: OK")

    import platform
    print(f"   platform: {platform.system()}")

    try:
        import netifaces
        print("   netifaces: OK")
        print(f"   Available interfaces: {netifaces.interfaces()}")
    except ImportError:
        print("   netifaces: MISSING")

except Exception as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

print("\n2. Testing argument parsing...")
try:
    parser = argparse.ArgumentParser()
    parser.add_argument('rps', type=float)
    parser.add_argument('interface', type=str)

    args = parser.parse_args()
    print(f"   Args: rps={args.rps}, interface={args.interface}")

except Exception as e:
    print(f"ARGPARSE ERROR: {e}")
    sys.exit(1)

print("\n3. Testing file reading...")
try:
    with open('urls.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    print(f"   Found {len(urls)} URLs: {urls}")
except FileNotFoundError:
    print("   urls.txt not found!")
    sys.exit(1)
except Exception as e:
    print(f"FILE ERROR: {e}")
    sys.exit(1)

print("\n4. Testing basic request...")
try:
    response = requests.get('https://httpbin.org/get', timeout=5)
    print(f"   Test request status: {response.status_code}")
except Exception as e:
    print(f"REQUEST ERROR: {e}")

print("\n=== DEBUG SCRIPT END ===")