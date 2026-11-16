import argparse

from .engine import initialize


def main():
    parser = argparse.ArgumentParser(description="Flowdesk workflow automation")
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web", help="Open the local workflow editor")
    web.add_argument("--port", type=int, default=8765)
    commands.add_parser("mcp", help="Run the MCP server using stdio")
    commands.add_parser("worker", help="Forward queued webhook deliveries")
    args = parser.parse_args()
    initialize()
    if args.command == "web":
        import uvicorn
        uvicorn.run("flowdesk.web:app", host="127.0.0.1", port=args.port, proxy_headers=False)
    elif args.command == "worker":
        from .worker import work
        work()
    else:
        from .mcp_server import server
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
