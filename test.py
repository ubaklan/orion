import asyncio
import aiohttp
import socket

class BindToDeviceTCPConnector(aiohttp.TCPConnector):
    def __init__(self, device_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name.encode()

    async def _wrap_create_connection(self, protocol_factory, host, port, *args, **kwargs):
        loop = self._loop

        def sock_factory():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            sock.setsockopt(socket.SOL_SOCKET, 25, self.device_name)  # SO_BINDTODEVICE
            return sock

        return await loop.create_connection(
            protocol_factory,
            host,
            port,
            *args,
            sock=sock_factory(),
            **kwargs,
        )

async def test_request():
    connector = BindToDeviceTCPConnector('enx020054323163')
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())

asyncio.run(test_request())
