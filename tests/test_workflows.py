import asyncio
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from starlette.testclient import TestClient

from flowdesk import engine
from flowdesk.web import app
from flowdesk.worker import send_one


class Workflows(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = str(Path(directory.name) / "db.sqlite")
        env = patch.dict(os.environ, FLOWDESK_DB=self.path)
        env.start()
        self.addCleanup(env.stop)
        engine.initialize()
        self.client = TestClient(app, base_url="http://localhost")
        self.addCleanup(self.client.close)
        self.definition = {"name": "Intake", "steps": [
            {"kind": "filter", "field": "type", "equals": "web"},
            {"kind": "record"},
            {"kind": "set", "field": "label", "template": "Hello {{name}}"},
            {"kind": "deliver", "destination": "crm"}]}
        self.flow = self.client.post("/api/workflows", json=self.definition).json()
        self.id = self.flow["id"]
        self.payload = {"type": "web", "name": "Ada"}

    def test_preview_and_failed_runs_have_no_effects(self):
        self.assertEqual(engine.run(self.id, self.payload, preview=True)["output"]["label"], "Hello Ada")
        self.assertEqual(engine.history(self.id), [])
        self.assertEqual(engine.run(self.id, {"type": "web"})["status"], "failed")
        self.assertEqual(engine.run(self.id, {"type": "other"})["status"], "filtered")
        self.assertEqual(engine.records(self.id), [])
        self.assertEqual(engine.deliveries(self.id), [])

    def test_hook_authentication_and_concurrent_retries(self):
        hook = f"/hooks/{self.id}"
        self.assertEqual(self.client.post(hook, json=self.payload).status_code, 403)
        key = self.client.get(f"/api/workflows/{self.id}/key").json()["key"]
        headers = {"X-Flowdesk-Key": key, "Idempotency-Key": "order-1"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: self.client.post(hook, headers=headers, json=self.payload).json()["id"], range(8)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(engine.history(self.id)), 1)
        self.assertEqual(len(engine.records(self.id)), 1)
        self.assertEqual(len(engine.deliveries(self.id)), 1)
        self.assertEqual(self.client.post(hook, headers=headers, json={}).status_code, 409)

    def test_validation_and_revision_conflicts(self):
        self.assertEqual(self.client.post("/api/workflows", json={"name": "bad", "steps": []}).status_code, 400)
        url = f"/api/workflows/{self.id}/save"
        body = {"revision": 1, "definition": self.definition}
        self.assertEqual(self.client.post(url, json=body).json()["revision"], 2)
        self.assertEqual(self.client.post(url, json=body).status_code, 409)
        self.assertEqual(self.client.get("/api/workflows", headers={"Host": "outside.test"}).status_code, 400)
        self.assertEqual(self.client.get("/api/workflows", headers={"Origin": "https://outside.test"}).status_code, 403)

    def test_worker_forwards_transformed_object_once(self):
        import json
        run = engine.run(self.id, self.payload)
        received = []
        def sink(request):
            received.append((request.headers["idempotency-key"], json.loads(request.content)))
            return httpx.Response(202)
        with httpx.Client(transport=httpx.MockTransport(sink)) as client:
            self.assertTrue(send_one({"crm": "https://receiver.example/hook"}, client))
            self.assertFalse(send_one({}, client))
        row, = engine.deliveries(self.id)
        self.assertEqual((row["run"], row["status"]), (run["id"], "sent"))
        self.assertEqual(received, [(row["id"], run["output"])])
        self.assertEqual(engine.records(self.id)[0]["data"], self.payload)

    def test_real_stdio_client_and_shared_database(self):
        async def check():
            params = StdioServerParameters(command=sys.executable, args=["-m","flowdesk","mcp"],
                                          env={"FLOWDESK_DB": self.path})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    tools = (await client.list_tools()).tools
                    self.assertEqual(len(tools), 8)
                    args = {"workflow_id": self.id, "payload": self.payload}
                    preview = await client.call_tool("preview_workflow", args)
                    self.assertFalse(preview.isError)
                    self.assertEqual(engine.history(self.id), [])
                    result = await client.call_tool("run_workflow", dict(args, event_id="abc"))
                    self.assertFalse(result.isError)
                    self.assertEqual(engine.history(self.id)[0]["status"], "completed")
                    created = await client.call_tool("create_workflow", {"definition": self.definition})
                    self.assertFalse(created.isError)
                    self.assertEqual(len(self.client.get("/api/workflows").json()), 2)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
