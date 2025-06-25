import aiohttp
import asyncio
import socket


class BindToDeviceConnector(aiohttp.TCPConnector):
    def _wrap_create_connection(self, protocol_factory, host, port, **kwargs):
        async def bind_socket():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, 25, b'enx020054323163\0')  # device name
            return sock

        self._factory = protocol_factory
        return super()._wrap_create_connection(protocol_factory, host, port, **kwargs)


async def main():
    connector = BindToDeviceConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())


asyncio.run(main())
