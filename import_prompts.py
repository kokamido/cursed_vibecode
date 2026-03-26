#!/usr/bin/env python3
"""Import system prompts from a JSON file into the database.

Usage: python import_prompts.py prompts.json

JSON format: [{"name": "...", "text": "..."}, ...]
"""

import asyncio
import json
import sys

from db import init_db, create_system_prompt


async def main(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: expected JSON array of {name, text}", file=sys.stderr)
        sys.exit(1)
    await init_db()
    for item in data:
        name = item.get("name", "").strip()
        text = item.get("text", "").strip()
        if not name or not text:
            print(f"Skipped (empty name or text): {item}", file=sys.stderr)
            continue
        prompt = await create_system_prompt(name, text)
        print(f"Imported: {prompt['name']} (id={prompt['id']})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <prompts.json>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
