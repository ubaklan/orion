#!/usr/bin/env python3
"""
HTTP Request Rate Limiter Script - Async Batch Version
Sends HTTP requests in batches to predefined URLs at a specified rate through a specific network interface.
Uses asyncio for true concurrent execution.
"""

import argparse
import time
import json
import socket
import asyncio
import aiohttp
from threading import Thread, Event
from queue import Queue
import urllib3
import sys
import platform

# Try to import netifaces, but make it optional
try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False
    print("Warning: netifaces not available. Install with: pip install netifaces")

# Suppress SSL warnings for testing purposes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def validate_interface(interface):
    """Validate that the network interface exists and is active."""
    if not NETIFACES_AVAILABLE:
        print(f"Warning: Cannot validate interface {interface} - netifaces not available")
        return True

    try:
        if interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                ip = addrs[netifaces.AF_INET][0]['addr']
                print(f"Interface {interface} found with IP: {ip}")
                return True
            else:
                print(f"Warning: Interface {interface} exists but has no IPv4 address")
                return False
        else:
            print(f"Error: Interface {interface} not found")
            print(f"Available interfaces: {', '.join(netifaces.interfaces())}")
            return False
    except Exception as e:
        print(f"Error checking interface {interface}: {e}")
        return False


def get_interface_ip(interface):
    """Get the IP address of the specified interface."""
    if not NETIFACES_AVAILABLE:
        return None

    try:
        if interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                return addrs[netifaces.AF_INET][0]['addr']
    except Exception as e:
        print(f"Error getting IP for interface {interface}: {e}")
    return None


async def make_request_async(session, url, headers=None, request_id=None, timeout=10, local_addr=None):
    """Make a single async HTTP request and return the result."""
    if headers is None or not headers:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Content-Type': 'text/plain;text/html',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
            'Cache-Control': 'no-cache',
            'Accept-Encoding': 'gzip, deflate, br'
        }

    try:
        print(f'[{request_id}] Sending async request to {url}')

        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with session.get(url, headers=headers, timeout=timeout_obj, allow_redirects=True) as response:
            text = await response.text()

            cookies = '; '.join([f"{k}={v}" for k, v in response.cookies.items()])

            result = {
                'request_id': request_id,
                'url': url,
                'status_code': response.status if 'NEXT_DATA' in text else 400,
                'headers': dict(response.headers),
                'cookies': cookies,
                'body_length': len(text),
                'success': 'NEXT_DATA' in text
            }

            print(f'[{request_id}] Request completed - Status: {result["status_code"]}, Success: {result["success"]}')
            return result

    except Exception as e:
        error_result = {
            'request_id': request_id,
            'url': url,
            'error': str(e),
            'success': False
        }
        print(f'[{request_id}] Request failed: {str(e)}')
        return error_result


async def send_batch_async(urls, batch_id, timeout=30, local_addr=None, max_concurrent=200):
    """Send a batch of requests asynchronously."""
    results = []

    # Create connector with local address binding if available
    connector_kwargs = {
        'limit': max_concurrent,
        'limit_per_host': max_concurrent,
        'ttl_dns_cache': 300,
        'use_dns_cache': True,
    }

    if local_addr:
        try:
            connector_kwargs['local_addr'] = (local_addr, 0)
        except Exception as e:
            print(f"Warning: Could not bind to local address {local_addr}: {e}")

    connector = aiohttp.TCPConnector(**connector_kwargs)

    async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout),
            trust_env=True
    ) as session:

        # Create all request tasks
        tasks = []
        for i, url_config in enumerate(urls):
            url = url_config.get('url')
            headers = url_config.get('headers', {})
            request_id = f"{batch_id}-{i+1}"

            task = make_request_async(session, url, headers, request_id, timeout, local_addr)
            tasks.append(task)

        # Execute all requests concurrently
        print(f"[BATCH {batch_id}] Executing {len(tasks)} concurrent requests...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                error_result = {
                    'request_id': f"{batch_id}-error",
                    'url': 'unknown',
                    'error': str(result),
                    'success': False
                }
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        return processed_results


def batch_rate_limited_requester_async(urls, batches_per_second, batch_size, stop_event, results_queue, max_concurrent=200, timeout=10, interface=None):
    interval = 1.0 / batches_per_second if batches_per_second > 0 else 1.0
    batch_count = 0

    local_addr = get_interface_ip(interface) if interface else None
    if local_addr:
        print(f"Using local address: {local_addr}")

    async def run_batches():
        nonlocal batch_count

        while not stop_event.is_set():
            batch_count += 1
            start_time = time.time()

            batch_urls = []
            for i in range(batch_size):
                url_index = (batch_count * batch_size + i) % len(urls)
                batch_urls.append(urls[url_index])

            print(f"\n[BATCH {batch_count}] Starting batch of {len(batch_urls)} requests...")

            try:
                batch_results = await send_batch_async(batch_urls, batch_count, timeout, local_addr, max_concurrent)

                for result in batch_results:
                    results_queue.put(result)

                print(f"[BATCH {batch_count}] Completed {len(batch_results)} requests")

            except Exception as e:
                print(f"[BATCH {batch_count}] Batch failed: {e}")

            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)

            if sleep_time > 0:
                print(f"[BATCH {batch_count}] Waiting {sleep_time:.2f}s for next batch...")
                await asyncio.sleep(sleep_time)

    try:
        asyncio.run(run_batches())
    except Exception as e:
        print(f"Async batch requester error: {e}")


def load_urls_from_file(filename="urls.txt"):
    """Load URLs from a text file, one URL per line."""
    try:
        with open(filename, 'r') as f:
            urls = []
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    urls.append({
                        "url": url,
                        "headers": {}
                    })
            return urls
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return None
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Send HTTP requests in batches at a specified rate through a network interface (async version)'
    )
    parser.add_argument(
        '--batches_per_second',
        type=float,
        required=True,
        help='Batches per second (e.g., 1.0 for 1 batch per second)'
    )
    parser.add_argument(
        '--batch_size',
        type=int,
        required=True,
        help='Number of requests per batch (e.g., 5 for 5 concurrent requests per batch)'
    )
    parser.add_argument(
        '--interface',
        type=str,
        help='Network interface name (e.g., eth0, wlan0)'
    )
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=200,
        help='Maximum number of concurrent connections (default: 200)'
    )
    parser.add_argument(
        '--urls-file',
        type=str,
        default='urls.txt',
        help='File containing URLs to request (default: urls.txt)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='Request timeout in seconds (default: 10)'
    )

    args = parser.parse_args()

    if args.interface and not validate_interface(args.interface):
        print(f"Interface validation failed. Continue anyway? (y/n): ", end='')
        if input().lower() != 'y':
            return

    urls = load_urls_from_file(args.urls_file)
    if urls is None or not urls:
        print(f"Error: No URLs found in {args.urls_file} file.")
        print(f"Please create {args.urls_file} file with one URL per line.")
        return

    total_rps = args.batches_per_second * args.batch_size

    print(f"Starting async batch rate limiter:")
    print(f"  - Batches per second: {args.batches_per_second}")
    print(f"  - Batch size: {args.batch_size}")
    print(f"  - Total requests per second: {total_rps}")
    print(f"  - Interface: {args.interface or 'default'}")
    print(f"  - URLs: {len(urls)} loaded from {args.urls_file}")
    print(f"  - Max concurrent connections: {args.max_concurrent}")
    print(f"  - Request timeout: {args.timeout}s")
    print(f"  - Duration: infinite")

    stop_event = Event()
    results_queue = Queue()

    requester_thread = Thread(
        target=batch_rate_limited_requester_async,
        args=(urls, args.batches_per_second, args.batch_size, stop_event, results_queue, args.max_concurrent, args.timeout, args.interface)
    )
    requester_thread.start()

    try:
        start_time = time.time()
        success_count = 0
        error_count = 0
        batch_count = 0

        while True:
            try:
                result = results_queue.get(timeout=1)
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1

                if (success_count + error_count) % args.batch_size == 0:
                    batch_count += 1
                    elapsed = time.time() - start_time
                    total_requests = success_count + error_count
                    actual_rps = total_requests / elapsed if elapsed > 0 else 0
                    actual_bps = batch_count / elapsed if elapsed > 0 else 0

                    print(f"\nStats after {batch_count} batches:")
                    print(f"  Total requests: {total_requests}")
                    print(f"  Successful: {success_count}")
                    print(f"  Errors: {error_count}")
                    print(f"  Actual rate: {actual_rps:.2f} req/s ({actual_bps:.2f} batches/s)")
                    print(f"  Target rate: {total_rps:.2f} req/s ({args.batches_per_second} batches/s)")

            except:
                # Timeout on queue get, continue
                pass

    except KeyboardInterrupt:
        print("\nShutdown requested by user...")

    finally:
        stop_event.set()
        requester_thread.join(timeout=10)

        elapsed = time.time() - start_time
        total_requests = success_count + error_count
        actual_rps = total_requests / elapsed if elapsed > 0 else 0
        actual_bps = batch_count / elapsed if elapsed > 0 else 0

        print(f"\nFinal Statistics:")
        print(f"  Total requests: {total_requests}")
        print(f"  Successful: {success_count}")
        print(f"  Errors: {error_count}")
        print(f"  Batches completed: {batch_count}")
        print(f"  Duration: {elapsed:.2f} seconds")
        print(f"  Actual rate: {actual_rps:.2f} requests/second")
        print(f"  Actual batch rate: {actual_bps:.2f} batches/second")
        print(f"  Target rate: {total_rps:.2f} requests/second")
        print(f"  Target batch rate: {args.batches_per_second} batches/second")


if __name__ == "__main__":
    main()