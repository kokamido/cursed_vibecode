# LLM Chat Client

A minimalistic web interface for chatting with LLM via the OpenAI Responses API, proxied through a local Python backend.

## Features

- Text chat with LLM (Gemini models via OpenAI-compatible API)
- Image attachment support (send images to the model)
- Image generation via `google/gemini-3-pro-image-preview`
- Persistent conversation history (SQLite)
- Markdown rendering in responses

## Requirements

- Python 3.12+

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running

```bash
python server.py
```

The app starts on **http://localhost:8083**.

Open it in your browser, enter your API key in the input field, and start chatting.

## Available Models

- **google/gemini-3-pro-preview** — text responses
- **google/gemini-3-pro-image-preview** — text + image generation
