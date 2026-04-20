import asyncio
import websockets
import sys

async def test():
    ports = [3001, 3006, 6099, 8090]
    for port in ports:
        uri = f"ws://127.0.0.1:{port}"
        print(f"--- Testing {uri} ---")
        try:
            async with websockets.connect(uri, open_timeout=2) as websocket:
                print(f"✅ Successfully established connection to {uri}!")
                await websocket.close()
                return
        except Exception as e:
            print(f"❌ Connection to {port} failed: {type(e).__name__}: {e}")
    # 所有端口测试完后再退出
    sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        pass
