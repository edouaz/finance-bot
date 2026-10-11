import unittest
from pathlib import Path
from datetime import timedelta
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class StdioTests(unittest.TestCase):
    def test_initialize_discover_and_safe_call(self):
        async def check():
            root=Path(__file__).resolve().parents[1]
            async with stdio_client(StdioServerParameters(command=str(root/'.venv/bin/python'),args=[str(root/'finance_mcp.py')])) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=15)) as session:
                    init=await session.initialize()
                    self.assertEqual(init.serverInfo.name,'Personal Finance Tracker v2')
                    tools=await session.list_tools()
                    self.assertGreaterEqual(len(tools.tools),15)
                    response=await session.call_tool('get_connection_status',{})
                    self.assertFalse(response.isError)
                    import json
                    self.assertNotIn('session_id',json.dumps(response.model_dump()))
                    invalid=await session.call_tool('get_transactions',{'start_date':'bad','end_date':'bad','limit':500})
                    self.assertTrue(invalid.isError or 'error' in str(invalid))
        anyio.run(check)
