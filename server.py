import asyncio
import json
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout
import aiohttp_cors

from db import (
    init_db, list_conversations, create_conversation, delete_conversation,
    rename_conversation, set_conversation_system_prompt,
    get_messages, add_message, delete_message,
    list_system_prompts, create_system_prompt, delete_system_prompt,
    list_endpoints, get_endpoint, create_endpoint, delete_endpoint,
)
STATIC_DIR = Path(__file__).parent / "static"
MODELS_FILE = Path(__file__).parent / "models.json"


async def index_handler(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def models_handler(request):
    with open(MODELS_FILE) as f:
        data = json.load(f)
    return web.json_response(data)


async def proxy_handler(request):
    """Proxy requests to the upstream API, preserving the sub-path."""
    sub_path = request.match_info.get("path", "responses")
    body = await request.read()

    endpoint_id = request.rel_url.query.get("endpoint_id")
    if not endpoint_id:
        return web.json_response({"error": "endpoint_id query param required"}, status=400)
    endpoint = await get_endpoint(int(endpoint_id))
    if not endpoint:
        return web.json_response({"error": "Endpoint not found"}, status=404)

    base_url = endpoint["base_url"].rstrip("/")
    headers = {
        "Authorization": f"Bearer {endpoint['api_key']}",
        "Content-Type": "application/json",
    }

    session: ClientSession = request.app["client_session"]
    try:
        async with session.post(
            f"{base_url}/v1/{sub_path}",
            data=body,
            headers=headers,
        ) as upstream_resp:
            resp_body = await upstream_resp.read()
            return web.Response(
                body=resp_body,
                status=upstream_resp.status,
                content_type="application/json",
            )
    except asyncio.TimeoutError:
        return web.json_response({"error": "Upstream request timed out"}, status=504)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


# ── Conversation endpoints ──

async def conversations_list_handler(request):
    convs = await list_conversations()
    return web.json_response(convs)


async def conversations_create_handler(request):
    conv = await create_conversation()
    return web.json_response(conv, status=201)


async def conversations_delete_handler(request):
    conv_id = int(request.match_info["id"])
    await delete_conversation(conv_id)
    return web.json_response({"ok": True})


async def conversations_patch_handler(request):
    conv_id = int(request.match_info["id"])
    data = await request.json()
    if "title" in data:
        title = data["title"].strip()
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        await rename_conversation(conv_id, title)
    if "system_prompt" in data:
        await set_conversation_system_prompt(conv_id, data["system_prompt"])
    return web.json_response({"ok": True})


# ── Message endpoints ──

async def messages_list_handler(request):
    conv_id = int(request.match_info["id"])
    msgs = await get_messages(conv_id)
    return web.json_response(msgs)


async def messages_create_handler(request):
    conv_id = int(request.match_info["id"])
    data = await request.json()
    role = data.get("role", "user")
    text = data.get("text", "")
    images = data.get("images", [])
    input_tokens = int(data.get("input_tokens", 0) or 0)
    output_tokens = int(data.get("output_tokens", 0) or 0)
    cost = data.get("cost")
    if cost is not None:
        cost = float(cost)
    msg = await add_message(conv_id, role, text, images, input_tokens, output_tokens, cost)
    return web.json_response(msg, status=201)


async def messages_delete_handler(request):
    msg_id = int(request.match_info["msg_id"])
    await delete_message(msg_id)
    return web.json_response({"ok": True})


# ── System Prompts Library endpoints ──

async def prompts_list_handler(request):
    prompts = await list_system_prompts()
    return web.json_response(prompts)


async def prompts_create_handler(request):
    data = await request.json()
    name = data.get("name", "").strip()
    text = data.get("text", "").strip()
    if not name or not text:
        return web.json_response({"error": "name and text required"}, status=400)
    prompt = await create_system_prompt(name, text)
    return web.json_response(prompt, status=201)


async def prompts_delete_handler(request):
    prompt_id = int(request.match_info["id"])
    await delete_system_prompt(prompt_id)
    return web.json_response({"ok": True})


# ── Endpoint endpoints ──

async def endpoints_list_handler(request):
    eps = await list_endpoints()
    return web.json_response(eps)


async def endpoints_create_handler(request):
    data = await request.json()
    name = data.get("name", "").strip()
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    cost_per_million_input = float(data.get("cost_per_million_input", 0) or 0)
    cost_per_million_output = float(data.get("cost_per_million_output", 0) or 0)
    if not name or not base_url:
        return web.json_response({"error": "name and base_url required"}, status=400)
    ep = await create_endpoint(name, base_url, api_key, cost_per_million_input, cost_per_million_output)
    return web.json_response(ep, status=201)


async def endpoints_delete_handler(request):
    ep_id = int(request.match_info["id"])
    await delete_endpoint(ep_id)
    return web.json_response({"ok": True})


async def on_startup(app):
    await init_db()
    timeout = ClientTimeout(total=300)
    app["client_session"] = ClientSession(timeout=timeout)


async def on_cleanup(app):
    await app["client_session"].close()


def create_app():
    app = web.Application(client_max_size=50 * 1024 * 1024)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    app.router.add_get("/", index_handler)
    app.router.add_get("/api/models", models_handler)
    app.router.add_post("/api/v1/{path:responses|chat/completions}", proxy_handler)

    # Conversation routes
    app.router.add_get("/api/conversations", conversations_list_handler)
    app.router.add_post("/api/conversations", conversations_create_handler)
    app.router.add_delete("/api/conversations/{id}", conversations_delete_handler)
    app.router.add_patch("/api/conversations/{id}", conversations_patch_handler)

    # Message routes
    app.router.add_get("/api/conversations/{id}/messages", messages_list_handler)
    app.router.add_post("/api/conversations/{id}/messages", messages_create_handler)
    app.router.add_delete("/api/conversations/{id}/messages/{msg_id}", messages_delete_handler)

    # System prompts library routes
    app.router.add_get("/api/prompts", prompts_list_handler)
    app.router.add_post("/api/prompts", prompts_create_handler)
    app.router.add_delete("/api/prompts/{id}", prompts_delete_handler)

    # Endpoint routes
    app.router.add_get("/api/endpoints", endpoints_list_handler)
    app.router.add_post("/api/endpoints", endpoints_create_handler)
    app.router.add_delete("/api/endpoints/{id}", endpoints_delete_handler)

    app.router.add_static("/static", STATIC_DIR, show_index=False)

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })

    for route in list(app.router.routes()):
        try:
            cors.add(route)
        except ValueError:
            pass

    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8083)
