#!/usr/bin/env python3
"""
HTTP Request Rate Limiter Script - Async Batch Version with Cookie Persistence
Sends HTTP requests in batches to predefined URLs at a specified rate through a specific IP address.
Uses asyncio for true concurrent execution and maintains cookies across batches.
"""

import argparse
import re
import time
import json
import socket
import asyncio
from typing import Optional

import aiohttp
from threading import Thread, Event, Lock
from queue import Queue

import requests
import urllib3
import sys
import platform
from collections import defaultdict
from bs4 import BeautifulSoup
import json
import ipaddress

# Try to import netifaces, but make it optional
try:
    import netifaces

    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False
    print("Warning: netifaces not available. Install with: pip install netifaces")

# Suppress SSL warnings for testing purposes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global cookie storage with thread-safe access
cookie_storage = defaultdict(dict)  # {domain: {cookie_name: cookie_value}}
cookie_lock = Lock()


class HTTPAdapterWithSocketOptions(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.socket_options = kwargs.pop("socket_options", None)
        super(HTTPAdapterWithSocketOptions, self).__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        if self.socket_options is not None:
            kwargs["socket_options"] = self.socket_options
        super(HTTPAdapterWithSocketOptions, self).init_poolmanager(*args, **kwargs)


class LocalAddressTCPConnector(aiohttp.TCPConnector):
    """Custom TCP connector that properly binds to a specific local interface."""

    def __init__(self, interface_name=None, *args, **kwargs):
        self.interface_name = interface_name
        super().__init__(*args, **kwargs)

    async def _create_connection(self, req, traces, timeout):
        """Override connection creation to bind to specific interface."""
        if self.interface_name:
            # Create socket and bind to interface
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Bind socket to specific interface
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface_name.encode())
                sock.setblocking(False)

                # Use the custom socket for connection
                return await self._loop.create_connection(
                    lambda: aiohttp.client_proto.ResponseHandler(loop=self._loop),
                    sock=sock
                )
            except Exception as e:
                sock.close()
                print(f"Failed to bind to interface {self.interface_name}: {e}")
                # Fall back to default behavior
                pass

        # Use default connection method
        return await super()._create_connection(req, traces, timeout)


def validate_ip_address(ip_str):
    """Validate that the provided string is a valid IP address."""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def get_interface_for_ip(target_ip):
    """Find the network interface that has the specified IP address."""
    if not NETIFACES_AVAILABLE:
        print(f"Warning: Cannot find interface for IP {target_ip} - netifaces not available")
        return None

    try:
        for interface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        if addr_info.get('addr') == target_ip:
                            print(f"Found IP {target_ip} on interface {interface}")
                            return interface
            except Exception as e:
                continue

        print(f"Warning: IP address {target_ip} not found on any interface")
        return None
    except Exception as e:
        print(f"Error finding interface for IP {target_ip}: {e}")
        return None


def validate_ip_on_system(ip_str):
    """Validate that the IP address exists on the system."""
    if not validate_ip_address(ip_str):
        print(f"Error: {ip_str} is not a valid IP address")
        return False

    if not NETIFACES_AVAILABLE:
        print(f"Warning: Cannot validate IP {ip_str} - netifaces not available")
        return True

    interface = get_interface_for_ip(ip_str)
    if interface:
        print(f"IP {ip_str} validated on interface {interface}")
        return True
    else:
        print(f"Error: IP {ip_str} not found on any network interface")
        available_ips = get_available_ips()
        if available_ips:
            print(f"Available IP addresses: {', '.join(available_ips)}")
        return False


def get_available_ips():
    """Get all available IP addresses on the system."""
    if not NETIFACES_AVAILABLE:
        return []

    ips = []
    try:
        for interface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip and ip != '127.0.0.1':  # Exclude localhost
                            ips.append(ip)
            except Exception:
                continue
    except Exception as e:
        print(f"Error getting available IPs: {e}")

    return ips


def get_domain_from_url(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return url


def get_cookies_for_domain(domain, idx):
    """Get stored cookies for a specific domain."""
    with cookie_lock:
        return cookie_storage.get(f"{domain}{str(idx)}", {}).copy()


def store_cookies_for_domain(domain, cookies, idx):
    """Store cookies for a specific domain."""
    with cookie_lock:
        if domain not in cookie_storage:
            cookie_storage[f"{domain}{str(idx)}"] = {}
        cookie_storage[f"{domain}{str(idx)}"].update(cookies)


def build_cookie_header(domain_cookies):
    """Build Cookie header string from stored cookies."""
    if not domain_cookies:
        return None
    return '; '.join([f"{k}={v}" for k, v in domain_cookies.items()])


def print_ip(local_ip):
    """Print the current external IP address using the specified local IP."""
    if local_ip and NETIFACES_AVAILABLE:
        interface = get_interface_for_ip(local_ip)
        if interface:
            try:
                adapter = HTTPAdapterWithSocketOptions(
                    socket_options=[(socket.SOL_SOCKET, 25, interface.encode('utf-8'))])
                session = requests.session()
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                response = session.get('https://ifconfig.io/ip', timeout=30)
                print("Current external IP: " + str(response.text.strip()))
            except Exception as e:
                print(f"Could not get external IP: {e}")
        else:
            print(f'WARN: Could not find interface for IP {local_ip}')
    else:
        print('WARN: Skipping IP check - no local IP specified or netifaces unavailable')


def restart_iface(local_ip):
    """Restart interface using the specified local IP."""
    if local_ip and NETIFACES_AVAILABLE:
        interface = get_interface_for_ip(local_ip)
        if interface:
            try:
                adapter = HTTPAdapterWithSocketOptions(
                    socket_options=[(socket.SOL_SOCKET, 25, interface.encode('utf-8'))])
                session = requests.session()
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                response = session.post('http://192.168.100.1/ajax', json={'funcNo': '1013'}, timeout=2)
                print("Restart response (text): " + str(response.text))
            except Exception as e:
                print(f"Interface restart failed: {e}")
        else:
            print(f'WARN: Could not find interface for IP {local_ip}')
    else:
        print('WARN: Skipping interface restart - no local IP specified or netifaces unavailable')


def extract_next_data_json(html_text):
    """Extract the JSON inside <script id="__NEXT_DATA__">...</script> using BeautifulSoup."""
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        script_tag = soup.select_one('script#__NEXT_DATA__')
        if script_tag and script_tag.string:
            return json.loads(script_tag.string)
    except Exception as e:
        print(f"[ERROR] Failed to extract __NEXT_DATA__: {e}")
    return None


async def send_batch_async(urls, batch_id, timeout=30, local_ip=None, max_concurrent=200):
    """Send a batch of requests asynchronously."""
    results = []

    # Get interface name for the local IP
    interface_name = None
    if local_ip and NETIFACES_AVAILABLE:
        interface_name = get_interface_for_ip(local_ip)
        if interface_name:
            print(f"[BATCH {batch_id}] Using interface: {interface_name} for IP: {local_ip}")
        else:
            print(f"[BATCH {batch_id}] Warning: Could not find interface for IP: {local_ip}")

    # Create connector with proper interface binding
    if interface_name:
        # Use custom connector that binds to interface
        connector = LocalAddressTCPConnector(
            interface_name=interface_name,
            limit=max_concurrent,
            limit_per_host=max_concurrent,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
    else:
        # Fallback to regular connector
        connector_kwargs = {
            'limit': max_concurrent,
            'limit_per_host': max_concurrent,
            'ttl_dns_cache': 300,
            'use_dns_cache': True,
        }

        if local_ip:
            try:
                connector_kwargs['local_addr'] = (local_ip, 0)
                print(f"[BATCH {batch_id}] Binding to local address: {local_ip}")
            except Exception as e:
                print(f"Warning: Could not bind to local address {local_ip}: {e}")

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
            request_id = f"{batch_id}-{i + 1}"

            task = make_request_async_using_requests(url, i, headers, request_id, timeout, local_ip)
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
                    'domain': 'unknown',
                    'error': str(result),
                    'success': False
                }
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        return processed_results


async def make_request_async_using_requests(url, idx, headers=None, request_id=None, timeout=10,
                                            local_ip: Optional[str] = None):
    if headers is None:
        headers = {}

    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Content-Type': 'text/plain;text/html',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
        'Cache-Control': 'no-cache',
        'Accept-Encoding': 'gzip, deflate'
    }

    merged_headers = {**default_headers, **headers}

    def blocking_request():
        print(f'[{request_id}] Sending blocking request to {url}')
        if local_ip and NETIFACES_AVAILABLE:
            interface = get_interface_for_ip(local_ip)
            if interface:
                    adapter = HTTPAdapterWithSocketOptions(
                        socket_options=[(socket.SOL_SOCKET, 25, interface.encode('utf-8'))])
                    session = requests.session()
                    session.mount("http://", adapter)
                    session.mount("https://", adapter)
                    return session.get(url, headers=merged_headers, timeout=timeout)
            else:
                print(f'WARN: Could not find interface for IP {local_ip}')
                return None
        else:
            print('WARN: Skipping interface restart - no local IP specified or netifaces unavailable')
            return requests.get(url, headers=merged_headers, timeout=timeout)


    try:
        # Run blocking requests.get() in threadpool without blocking event loop
        response = await asyncio.to_thread(blocking_request)
        text = response.text
        data = extract_next_data_json(text)

        success = data is not None
        posted = False
        if success:
            # if post_extracted_data_item is async, await it
            posted = await post_extracted_data_item(data)

        result = {
            'request_id': request_id,
            'url': url,
            'status_code': response.status_code if success else 400,
            'success': success and posted,
            'posted': posted,
            'body_length': len(text),
        }

        print(
            f'[{request_id}] Request completed - Status: {result["status_code"]}, Success: {result["success"]}, text: {text}')
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


def batch_rate_limited_requester_async(urls, batches_per_second, batch_size, stop_event, results_queue,
                                       max_concurrent=200, timeout=10, local_ip=None):
    interval = 1.0 / batches_per_second if batches_per_second > 0 else 1.0
    batch_count = 0

    if local_ip:
        print(f"Using local IP address: {local_ip}")

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

            # Show current cookie state
            with cookie_lock:
                total_domains = len(cookie_storage)
                total_cookies = sum(len(cookies) for cookies in cookie_storage.values())
                if total_cookies > 0:
                    print(f"[BATCH {batch_count}] Cookie state: {total_cookies} cookies across {total_domains} domains")

            try:
                print_ip(local_ip)
                batch_results = await send_batch_async(batch_urls, batch_count, timeout, local_ip, max_concurrent)

                for result in batch_results:
                    results_queue.put(result)

                print(f"[BATCH {batch_count}] Completed {len(batch_results)} requests")
                restart_iface(local_ip)

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


def print_cookie_summary():
    """Print a summary of stored cookies."""
    with cookie_lock:
        if not cookie_storage:
            print("No cookies stored.")
            return

        print("\nCookie Summary:")
        total_cookies = 0
        for domain, cookies in cookie_storage.items():
            total_cookies += len(cookies)
            print(f"  {domain}: {len(cookies)} cookies")
        print(f"Total: {total_cookies} cookies across {len(cookie_storage)} domains")


async def post_extracted_data_item(data):
    url = 'https://core-data-api.threecolts.com/raw-walmart/categories'
    headers = {
        'x-api-key': 'b9e0cfc7-9ba4-43b9-b38f-3191d1f8d686',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                resp_text = await resp.text()
                print(f"[POST] Status: {resp.status}, Response: {resp_text[:100]}")
                return resp.status < 400
        except Exception as e:
            print(f"[POST] Failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Send HTTP requests in batches at a specified rate through a specific IP address (async version with cookie persistence)'
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
        '--local_ip',
        type=str,
        help='Local IP address to bind to (e.g., 192.168.1.100)'
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

    if args.local_ip and not validate_ip_on_system(args.local_ip):
        print(f"IP address validation failed. Continue anyway? (y/n): ", end='')
        if input().lower() != 'y':
            return

    urls = load_urls_from_file(args.urls_file)
    if urls is None or not urls:
        print(f"Error: No URLs found in {args.urls_file} file.")
        print(f"Please create {args.urls_file} file with one URL per line.")
        return

    total_rps = args.batches_per_second * args.batch_size

    print(f"Starting async batch rate limiter with cookie persistence:")
    print(f"  - Batches per second: {args.batches_per_second}")
    print(f"  - Batch size: {args.batch_size}")
    print(f"  - Total requests per second: {total_rps}")
    print(f"  - Local IP: {args.local_ip or 'default'}")
    print(f"  - URLs: {len(urls)} loaded from {args.urls_file}")
    print(f"  - Max concurrent connections: {args.max_concurrent}")
    print(f"  - Request timeout: {args.timeout}s")
    print(f"  - Duration: infinite")
    print(f"  - Cookie persistence: enabled")

    stop_event = Event()
    results_queue = Queue()

    requester_thread = Thread(
        target=batch_rate_limited_requester_async,
        args=(
            urls, args.batches_per_second, args.batch_size, stop_event, results_queue, args.max_concurrent,
            args.timeout,
            args.local_ip)
    )
    requester_thread.start()

    try:
        start_time = time.time()
        success_count = 0
        error_count = 0
        batch_count = 0
        total_new_cookies = 0

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
                    print(f"  New cookies collected: {total_new_cookies}")
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
        print(f"  Total new cookies collected: {total_new_cookies}")

        print_cookie_summary()


if __name__ == "__main__":
    main()
