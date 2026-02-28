# About the project

This is a minimalistic web-interface allowing user to chat with LLM via OpenAI openai responses API. It will run only on local machine so we can skip all the "production-ready" things like https, fault tolerance, advanced security, etc.

It's crucial to use OpenAI responses API format, not native Google lib.

# Project Doc

## Overview
Local LLM chat web UI. Backend proxies requests to OpenAI-compatible APIs.
Run: `python server.py` → http://localhost:8083

## File Structure
```
server.py          # aiohttp backend, all API routes
db.py              # aiosqlite DB layer (data/chat.db)
requirements.txt   # aiohttp, aiohttp-cors, aiosqlite
static/
  index.html       # single-page app (Vue 3 CDN)
  js/app.js        # all Vue logic (~700 lines)
  css/style.css    # all styles
data/chat.db       # SQLite persistent storage
```

## Backend API Routes (`server.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves index.html |
| GET | `/api/models` | Returns models.json |
| POST | `/api/v1/responses?endpoint_id=N` | Proxy → `{base_url}/v1/responses` |
| POST | `/api/v1/chat/completions?endpoint_id=N` | Proxy → `{base_url}/v1/chat/completions` |
| GET/POST | `/api/conversations` | List / create |
| DELETE/PATCH | `/api/conversations/{id}` | Delete / update (title, system_prompt) |
| GET/POST | `/api/conversations/{id}/messages` | List / add message |
| DELETE | `/api/conversations/{id}/messages/{msg_id}` | Delete message |
| GET/POST | `/api/prompts` | System prompt library |
| DELETE | `/api/prompts/{id}` | Delete saved prompt |
| GET/POST | `/api/endpoints` | Provider endpoints |
| DELETE | `/api/endpoints/{id}` | Delete endpoint |

## Database Schema (`db.py`)

- **conversations**: id, title, system_prompt, created_at, updated_at
- **messages**: id, conversation_id, role (user/assistant), text, sort_order, input_tokens, output_tokens, cost (REAL), created_at
- **message_images**: id, message_id, data_url (base64)
- **system_prompts**: id, name, text, created_at
- **endpoints**: id, name, base_url, api_key, cost_per_million_input, cost_per_million_output, api_format (responses|chat_completions), created_at

Auto-title: first user message (max 50 chars) becomes conversation title.

## Frontend (`static/js/app.js`)

Vue 3 CDN (no build step). CDN libs: marked, highlight.js, DOMPurify, KaTeX.

**Key Vue data:**
- `messages`, `conversations`, `activeConversationId`
- `endpoints`, `activeEndpointId` (persisted in localStorage)
- `models`, `selectedModel`
- `systemPrompt`, `savedPrompts`, `showPromptPanel`
- `attachedImages` (base64 JPEG ≤1024px), `attachedDocs` (.md files as text)

**API format selection logic:**
- `isImageModel()`: model has `api_type === 'chat_completions'` in models.json
- `shouldUseChatCompletions()`: image model OR endpoint's `api_format === 'chat_completions'`
- Responses API: system prompt as `role: 'developer'`, images as `input_image`
- Chat Completions: system prompt as `role: 'system'`, images as `image_url`; image model adds `extra_body: {modalities: ['image']}`

**Image generation:** `gemini-3-pro-image-preview` uses chat_completions. Response images parsed from `msg.images[].b64_json` or from error body regex (API quirk).

**Cost tracking:** `cost = (inputTokens/1M)*cost_per_million_input + (outputTokens/1M)*cost_per_million_output`, displayed in ₽ under assistant messages.

**Markdown:** marked → KaTeX ($$display$$, $inline$) → DOMPurify sanitize.

**URL routing:** Hash-based `#/chat/{id}`, popstate via hashchange event.

## Key Behaviors
- Drag & drop images or .md files onto chat area
- .md files sent as fenced code block user messages: `` ```markdown\n{content}\n``` ``
- Images resized client-side to max 1024px, JPEG 0.85 quality
- System prompt auto-saved on 500ms debounce after typing
- Retry button: removes last assistant message, re-calls LLM
- Conversation deleted → switches to next or creates new
