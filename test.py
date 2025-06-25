import aiohttp
import asyncio

async def test_request(local_ip):
    connector = aiohttp.TCPConnector(local_addr=(local_ip, 0))
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://httpbin.org/ip") as resp:
            print(await resp.text())

asyncio.run(test_request("192.168.100.110"))
