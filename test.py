import asyncio
import aiohttp
import socket

class BindToDeviceTCPConnector(aiohttp.TCPConnector):
    def __init__(self, device_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name.encode()

    async def _create_connection(self, req, *args, **kwargs):
        # This method creates the connection socket
        # We override it to create a socket with SO_BINDTODEVICE set

        loop = self._loop

        def _sock_factory():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Bind to device, Linux-only and requires privileges
            sock.setsockopt(socket.SOL_SOCKET, 25, self.device_name)  # 25 is SO_BINDTODEVICE
            sock.setblocking(False)
            return sock

        kwargs['sock'] = _sock_factory()

        return await super()._create_connection(req, *args, **kwargs)

async def test_request():
    connector = BindToDeviceTCPConnector('enx020054323163')
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())

asyncio.run(test_request())
