# Flowdesk MCP

A free, local-first alternative for Pabbly Connect-style workflows. Receive a JSON event, filter it, transform fields, save a record and forward the result to an HTTPS receiver. Build the same workflow in a browser or through an MCP client. The editor, webhook handler and MCP server share a SQLite database.

## Run the editor

Use Python 3.11 or newer. From a terminal:

```sh
git clone https://github.com/akash-decoder/flowdesk-mcp.git
cd flowdesk-mcp
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\activate.bat` in Windows Command Prompt. Then run:

```sh
python -m pip install .
flowdesk web
```

Open **http://127.0.0.1:8765**. The initial **Lead intake** draft accepts website inquiries, builds a subject line and stores the transformed record. Choose **Save workflow**, then **Preview**. The sample produces `Quote request from Alex`. Choose **Run now** and open **Records** to see the saved result. Change `service` to `print` and run again to see a filtered event in **Run history**.

## Connect an MCP client

For a desktop client that supports stdio, add this entry to its MCP server configuration. Replace the command with the absolute path to the installed Python interpreter. On Windows use a path such as `C:/projects/flowdesk-mcp/.venv/Scripts/python.exe`. Restart the client after saving.

```json
{
  "mcpServers": {
    "flowdesk": {
      "command": "/absolute/path/to/flowdesk-mcp/.venv/bin/python",
      "args": ["-m", "flowdesk", "mcp"]
    }
  }
}
```

Try asking your client:

> Find my Lead intake workflow. Preview it with name Alex and service website. Show me the transformed record.

| Tool | Operation |
| --- | --- |
| `list_workflows` | Read definitions, IDs and revisions |
| `create_workflow` | Create a named workflow with ordered steps |
| `update_workflow` | Save edits against an expected revision |
| `preview_workflow` | Evaluate an input without writing history or triggering actions |
| `run_workflow` | Execute a workflow with an optional idempotent event ID |
| `list_runs` | Read the latest 50 run outputs and step traces |
| `list_records` | Read the latest 100 saved records |
| `list_deliveries` | Read the latest 100 outbound delivery states |

## Receive an event

Save a workflow and open **Inbound webhook → Show connection details** in the editor. Supply the displayed workflow ID and key in your sender. For example, in a POSIX shell:

```sh
curl -X POST "http://127.0.0.1:8765/hooks/$WORKFLOW_ID" \
  -H "Content-Type: application/json" \
  -H "X-Flowdesk-Key: $WORKFLOW_KEY" \
  -H "Idempotency-Key: inquiry-001" \
  -d '{"name":"Alex","service":"website"}'
```

Retries with the same event ID and payload return the original run. Reusing the ID with different input returns HTTP 409. A processed event returns the run ID and workflow status. A filtered or failed workflow commits its run trace and creates zero records or deliveries.

## Send to another app

Add a **Send webhook** step and give it a destination alias, for example `crm`. Its body is the current JSON object. Start a worker from the same environment and OS user. Replace the example URL with the HTTPS webhook URL of your receiver.

```sh
export FLOWDESK_TARGETS='{"crm":"https://receiver.example/webhooks/intake"}'
flowdesk worker
```

On PowerShell, set `$env:FLOWDESK_TARGETS = '{"crm":"https://receiver.example/webhooks/intake"}'` and run `flowdesk worker`. Keep destination URLs with embedded credentials private. The worker sends each delivery with an `Idempotency-Key` header. Workflow completion queues the delivery. Its eventual HTTP outcome appears under **Deliveries**. A transport failure or an interrupted send is marked `unknown` after reconciliation. Check the receiver before manually resubmitting an event with a new ID.

## Operating scope

- MIT-licensed software with no subscription or per-run billing. Hosting and external services have their own terms and costs.
- Designed for one trusted local user. The editor listens on loopback. Local processes can read workflow data and webhook keys. For an external sender, forward only the specific `POST /hooks/<id>` endpoint through an HTTPS reverse proxy, forwarding the internal Host as `127.0.0.1`. Keep the editor and `/api` local.
- All three processes use `~/.flowdesk/workspace.sqlite3` by default. To share another location, give each process the same absolute `FLOWDESK_DB` path. Keep the database private and stop all three processes before copying its directory for a backup.
- Templates reference top-level JSON fields with `{{field}}`. Filters compare a field with a string using exact equality. A saved record captures the payload at that step. A workflow supports 24 ordered steps and 64 KiB input/output objects.
- This release focuses on workflow automation. The wider Pabbly suite, its native integration catalog, scheduling and OAuth account management are outside the implementation. [Public product review](docs/product-review.md)

## Tests

```sh
python -m unittest discover -s tests -v
```

The tests exercise the editor API, concurrent webhook retries, filter and failure behavior, outbound delivery with a mock HTTPS receiver, and a real MCP client/server exchange over stdio. For the desktop/mobile browser smoke test, install Playwright, run `python -m playwright install chromium`, then `python tests/browser_smoke.py`.
