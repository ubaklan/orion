import aiohttp
import asyncio
import socket


def create_bound_socket(interface: str, local_ip: str) -> socket.socket:
    """Create a socket bound to a specific device and IP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind to interface (Linux only, requires root)
    SO_BINDTODEVICE = 25
    sock.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, interface.encode() + b'\0')

    # Bind to local IP
    sock.bind((local_ip, 0))

    return sock


async def main():
    interface = "enx020054323163"
    local_ip = "192.168.100.110"

    def socket_factory():
        return create_bound_socket(interface, local_ip)

    connector = aiohttp.TCPConnector(socket_factory=socket_factory)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())


if __name__ == "__main__":
    asyncio.run(main())
