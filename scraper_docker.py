#!/usr/bin/env python3

import subprocess
import threading
import time
import argparse
from queue import Queue


def load_urls(file_path):
    with open(file_path, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def fetch_url(request_id, url):
    docker_cmd = [
        "docker", "run", "--platform", "linux/amd64", "--rm",
        "lwthiker/curl-impersonate:0.5-chrome",
        "curl_chrome110",
        url,
    ]

    print(docker_cmd)

    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        body = result.stdout
        print(body)
        success = "NEXT_DATA" in body
        print(f"[{request_id}] {url} -> {'✅' if success else '❌'}")
    except Exception as e:
        print(f"[{request_id}] {url} -> ERROR: {e}")

def worker(thread_id, task_queue):
    while True:
        try:
            request_id, url = task_queue.get(timeout=1)
        except:
            return
        fetch_url(request_id, url)
        task_queue.task_done()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="urls.txt")
    parser.add_argument("--threads", type=int, default=5)
    parser.add_argument("--rate", type=float, default=1.0, help="Requests per second per thread")
    args = parser.parse_args()

    urls = load_urls(args.file)
    task_queue = Queue()

    for i, url in enumerate(urls):
        task_queue.put((i + 1, url))

    threads = []
    for t_id in range(args.threads):
        t = threading.Thread(target=worker, args=(t_id, task_queue))
        t.start()
        threads.append(t)
        time.sleep(1.0 / args.rate)  # Stagger thread startup to rate-limit

    task_queue.join()


if __name__ == "__main__":
    main()
