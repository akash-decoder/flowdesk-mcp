from pathlib import Path

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import engine

STATIC = Path(__file__).with_name("static")


async def body(request: Request):
    import json
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise ValueError("Use Content-Type application/json")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 131072:
            raise ValueError("Request exceeds 128 KiB")
        data.extend(chunk)
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


async def api(request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"error": "Cross-origin requests are disabled"}, 403)
    flow_id = request.path_params.get("flow_id")
    action = request.path_params.get("action")
    try:
        if request.url.path.startswith("/hooks/"):
            result = engine.run(flow_id, await body(request), request.headers.get("idempotency-key"),
                                hook_secret=request.headers.get("x-flowdesk-key", ""))
            return JSONResponse({"id": result["id"], "status": result["status"]})
        if request.method == "GET":
            if not flow_id:
                result = engine.workflows()
            elif action == "key":
                with engine.database() as db:
                    result = {"key": engine.lookup(db, flow_id)["secret"]}
            else:
                readers = {"runs": engine.history, "records": engine.records, "deliveries": engine.deliveries}
                if action not in readers:
                    return JSONResponse({"error": "Unknown endpoint"}, 404)
                result = readers[action](flow_id)
        else:
            data = await body(request)
            if not flow_id:
                result = engine.save(engine.Workflow.model_validate(data))
            elif action == "save":
                result = engine.save(engine.Workflow.model_validate(data.get("definition")), flow_id, data.get("revision"))
            elif action in ("run", "preview"):
                result = engine.run(flow_id, data.get("payload"), data.get("event_id"), preview=action == "preview")
            else:
                return JSONResponse({"error": "Unknown endpoint"}, 404)
        return JSONResponse(result)
    except ValidationError as exc:
        message = "; ".join(f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"error": message}, 400)
    except engine.Conflict as exc:
        return JSONResponse({"error": str(exc)}, 409)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, 403)
    except KeyError:
        return JSONResponse({"error": "Workflow not found"}, 404)
    except (ValueError, RecursionError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, 400)


async def asset(request):
    name = request.path_params.get("filename", "index.html")
    if name not in ("index.html", "app.js", "style.css"):
        return JSONResponse({"error": "File not found"}, 404)
    return FileResponse(STATIC / name)


app = Starlette(routes=[
    Route("/", asset), Route("/static/{filename}", asset),
    Route("/api/workflows", api, methods=["GET", "POST"]),
    Route("/api/workflows/{flow_id}/{action}", api, methods=["GET", "POST"]),
    Route("/hooks/{flow_id}", api, methods=["POST"]),
])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


async def headers(request, call_next):
    response = await call_next(request)
    response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"})
    return response
app.add_middleware(BaseHTTPMiddleware, dispatch=headers)
