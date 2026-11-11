# TheBoys

A minimal Streamlit chatbot on Groq. It sends the model exactly what you type, with no filters or guardrails, and lets you attach documents to ask about them.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Put your Groq key in `.env`, then start the app:

```bash
.venv/bin/streamlit run app.py
```

It opens at http://localhost:8501.

## System prompt

Write your system prompt in `sys_prompt.txt`. When that file is empty or missing, no system prompt is sent. It is read on every message, so edits apply immediately. The app never shows it, and nobody can change it from the chat.

`.env` and `sys_prompt.txt` are git-ignored, so your key and prompt stay on your machine.

## Documents

Use the paperclip in the message box to attach PDF, DOCX, TXT, MD, CSV, JSON, HTML or Python files. Their text is added to your message, up to 24,000 characters per file. Scanned PDFs need OCR first.

## Sharing on your network

Others on your network can connect if you start the app with `--server.address 0.0.0.0` and give them your computer's address on port 8501.
