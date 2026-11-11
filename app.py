"""TheBoys: a minimal Groq chatbot.

The model gets exactly what you type, plus any attached documents. The only
system prompt is the one in sys_prompt.txt, which is never shown in the app.
"""
import io
import os
import re
from pathlib import Path

import docx2txt
import groq
import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader

ROOT = Path(__file__).parent
SYS_PROMPT_FILE = ROOT / "sys_prompt.txt"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_DOC_CHARS = 24_000  # roughly 6k tokens, so a document fits Groq's free-tier limit
HISTORY_MESSAGES = 20  # older turns are not sent, to keep requests small
DOC_TYPES = ["pdf", "docx", "txt", "md", "csv", "json", "html", "py"]
NOT_CHAT = re.compile(r"whisper|orpheus|playai|tts|guard", re.I)

load_dotenv(ROOT / ".env", override=True)  # re-read on every rerun, so a new key applies at once
st.set_page_config(page_title="TheBoys", page_icon="💬")


def system_prompt() -> str:
    """Read fresh on every message, so edits apply without a restart."""
    try:
        return SYS_PROMPT_FILE.read_text().strip()
    except FileNotFoundError:
        return ""


@st.cache_resource
def client(api_key: str) -> groq.Groq:
    return groq.Groq(api_key=api_key)


@st.cache_data(ttl=600, show_spinner=False)
def chat_models(api_key: str) -> list[str]:
    try:
        listing = client(api_key).models.list().data
    except groq.GroqError:
        return [DEFAULT_MODEL]
    names = sorted(m.id for m in listing if getattr(m, "active", True) and not NOT_CHAT.search(m.id))
    return names or [DEFAULT_MODEL]


def read_document(upload) -> str:
    data = upload.getvalue()
    name = upload.name.lower()
    if name.endswith(".pdf"):
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        return docx2txt.process(io.BytesIO(data))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def attach(uploads) -> tuple[list[str], list[str]]:
    """Return document blocks for the model, and warnings for the user."""
    blocks, warnings = [], []
    for upload in uploads:
        try:
            text = read_document(upload).strip()
        except Exception as exc:
            warnings.append(f"Couldn't read {upload.name}: {exc}")
            continue
        if not text:
            warnings.append(f"{upload.name} has no readable text. Scanned PDFs need OCR first.")
            continue
        if len(text) > MAX_DOC_CHARS:
            warnings.append(f"{upload.name} is long, so only its first {MAX_DOC_CHARS:,} characters were sent.")
            text = text[:MAX_DOC_CHARS]
        blocks.append(f'<document name="{upload.name}">\n{text}\n</document>')
    return blocks, warnings


def stream_reply(api_key: str, model: str, history: list[dict]):
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_MESSAGES:]]
    prompt = system_prompt()
    if prompt:
        messages.insert(0, {"role": "system", "content": prompt})
    stream = client(api_key).chat.completions.create(model=model, messages=messages, stream=True)
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def error_text(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"].get("message", str(exc))
    return str(exc)


if "messages" not in st.session_state:
    st.session_state.messages = []

api_key = os.getenv("GROQ_API_KEY", "").strip()

with st.sidebar:
    st.title("TheBoys")
    if api_key:
        models = chat_models(api_key)
        model = st.selectbox("Model", models, index=models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0)
    if st.button("New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption("Attach documents with the paperclip in the message box to ask about them.")

if not api_key:
    st.info("Add your Groq key to the `.env` file as `GROQ_API_KEY=...`, then refresh this page.")
    st.stop()

if not st.session_state.messages:
    st.markdown(
        "<div style='text-align:center;padding-top:22vh'>"
        "<h1 style='font-size:3.2rem;margin-bottom:0'>TheBoys</h1>"
        "<p style='opacity:.6'>Ask anything, or attach a document to have it explained.</p></div>",
        unsafe_allow_html=True,
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["shown"])
        if message.get("files"):
            st.caption("📎 " + ", ".join(message["files"]))

sent = st.chat_input("Message TheBoys", accept_file="multiple", file_type=DOC_TYPES)
if sent:
    blocks, warnings = attach(sent.files)
    for warning in warnings:
        st.warning(warning)
    if sent.text or blocks:
        names = [upload.name for upload in sent.files]
        user = {
            "role": "user",
            "content": "\n\n".join([*blocks, sent.text] if sent.text else blocks),
            "shown": sent.text or "Uploaded " + ", ".join(names),
            "files": names,
        }
        st.session_state.messages.append(user)
        with st.chat_message("user"):
            st.markdown(user["shown"])
            if names:
                st.caption("📎 " + ", ".join(names))

        with st.chat_message("assistant"):
            try:
                reply = st.write_stream(stream_reply(api_key, model, st.session_state.messages))
            except groq.GroqError as exc:
                st.error(error_text(exc))
                st.session_state.messages.pop()  # so the failed message isn't resent next time
            else:
                text = reply if isinstance(reply, str) else "".join(map(str, reply))
                st.session_state.messages.append({"role": "assistant", "content": text, "shown": text})
