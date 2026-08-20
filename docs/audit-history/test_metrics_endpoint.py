"""Test script to verify metrics endpoint (R5-2)."""

import asyncio
from http.client import HTTPConnection

from loats.main import TradingSystem, settings


async def test_metrics_endpoint():
    """Test that metrics endpoint responds on http://localhost:8001/."""
    ts = None
    try:
        # Check settings
        print(f"Settings metrics_port: {settings.metrics_port}")

        # Initialize trading system (which should start metrics server)
        ts = TradingSystem()

        # Initialize the system (this should start the metrics server)
        print("Initializing trading system...")
        await ts.initialize()

        # Give the server time to start
        print("Waiting for metrics server to start...")
        await asyncio.sleep(2)

        # Test the metrics endpoint
        print(f"Connecting to http://localhost:{settings.metrics_port}/")
        try:
            conn = HTTPConnection("localhost", settings.metrics_port)
            conn.request("GET", "/")
            response = conn.getresponse()

            print(f"Response status: {response.status}")
            print(f"Response headers: {response.getheaders()}")

            body = response.read()
            print(
                f"Response body (first 500 chars): "
                f"{body[:500].decode('utf-8', errors='ignore')}"
            )

            if response.status == 200:
                print("[OK] Metrics endpoint is responding correctly!")
                conn.close()
                return True
            else:
                print(f"[FAIL] Metrics endpoint returned status {response.status}")
                conn.close()
                return False
        except Exception as e:
            print(f"[FAIL] Error connecting to metrics endpoint: {e}")
            return False
    except Exception as e:
        print(f"Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # Clean up
        print("Cleaning up...")
        if ts:
            try:
                await ts.shutdown()
            except Exception as e:
                print(f"Error during shutdown: {e}")


if __name__ == "__main__":
    result = asyncio.run(test_metrics_endpoint())
    exit(0 if result else 1)
