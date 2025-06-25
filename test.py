import aiohttp
import asyncio
import socket
from typing import Optional


class BindToDeviceConnector(aiohttp.TCPConnector):
    def __init__(self, interface: str, local_ip: str, *args, **kwargs):
        self.interface = interface
        self.local_ip = local_ip
        super().__init__(*args, **kwargs)

    async def _wrap_create_connection(
            self,
            protocol_factory,
            host: str,
            port: int,
            *,
            ssl: Optional[bool] = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: Optional[socket.socket] = None,
            local_addr=None,
            server_hostname=None,
    ):
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Bind to interface (SO_BINDTODEVICE = 25)
        sock.setsockopt(socket.SOL_SOCKET, 25, self.interface.encode() + b"\0")

        # Bind to specific local IP
        sock.bind((self.local_ip, 0))

        return await super()._wrap_create_connection(
            protocol_factory,
            host,
            port,
            ssl=ssl,
            family=family,
            proto=proto,
            flags=flags,
            sock=sock,
            local_addr=local_addr,
            server_hostname=server_hostname,
        )


async def main():
    # Replace with your interface and IP
    interface = "enx020054323163"
    local_ip = "192.168.100.110"

    connector = BindToDeviceConnector(interface=interface, local_ip=local_ip)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())


if __name__ == "__main__":
    asyncio.run(main())
