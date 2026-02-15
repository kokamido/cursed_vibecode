# About the project

This is a minimalistic web-interface allowing user to chat with LLM via OpenAI openai responses API. It will run only on local machine so we can skip all the "production-ready" things like https, fault tolerance, advanced security, etc.

It's crucial to use OpenAI responses API format, not native Google lib.

# Features

- Web chat with LLM, allowing user to:
    - write text messages
    - attach pictures
    - read the answer from the model 

- Two model available to choise: 
    - gemini-3-pro-preview - it answers with text
    - google/gemini-3-pro-image-preview - it may generate pictures and answer with text

- Hardcoded base url for LLM api: https://api.vsellm.ru. Maybe we need some kind of ridiculous simple backend to deal with CORS.

- Api key proided by the user via input field on the frontend. It's appropriate to store it in cookie.

- Markdown in dialog is pretty formatted

- There is an clean way to send the image generation request to google/gemini-3-pro-image-preview

- Persistent store for dialogs and pictures

- It should be possible to set a system prompt in interface. This prompt should be provided to LLM as first message in the chat with role 'system'. User can save prompt and reuse it further, maybe using dropdown with saved prompt or other interface element. If system prompt is empty then message with role 'system' should not be injected in chat.


# Tech stack

Backend - python + aiohttp

Front - HTML, CSS, Vue JS


