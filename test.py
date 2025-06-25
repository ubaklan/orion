import socket
import aiohttp
import asyncio

class BindToDeviceTCPConnector(aiohttp.TCPConnector):
    def __init__(self, device_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name

    async def _wrap_create_connection(self, protocol_factory, host, port, **kwargs):
        def factory():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Bind to interface:
            sock.setsockopt(socket.SOL_SOCKET, 25, self.device_name.encode())  # 25 is SO_BINDTODEVICE
            sock.setblocking(False)
            return sock

        return await self._loop.create_connection(protocol_factory, host, port, sock=factory(), **kwargs)

async def test_request():
    connector = BindToDeviceTCPConnector('enx020054323163')
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())

asyncio.run(test_request())
