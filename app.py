import hashlib
import io
import json
import os
import re

import streamlit as st
import streamlit.components.v1 as components
from audiorecorder import audiorecorder
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment
from static_ffmpeg import run as static_ffmpeg_run

_ffmpeg_path, _ffprobe_path = static_ffmpeg_run.get_or_fetch_platform_executables_else_raise()
AudioSegment.converter = _ffmpeg_path
os.environ["PATH"] = os.path.dirname(_ffmpeg_path) + os.pathsep + os.environ.get("PATH", "")

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LLM_MODEL = "gpt-4o-mini"

MENU = """**Tapas**
- Patatas bravas - 4,50€
- Tortilla española - 5,00€
- Croquetas de jamón - 6,00€
- Gambas al ajillo - 7,50€
- Pan con tomate - 3,00€
- Aceitunas - 2,50€

**Bebidas**
- Agua - 1,50€
- Vino tinto - 3,00€
- Vino blanco - 3,00€
- Cerveza - 2,50€
- Sangría - 4,00€"""

SYSTEM_PROMPT = (
    "You are a friendly waiter at a tapas bar in Madrid. The user is an A2 "
    "Spanish learner trying to order food. Respond in simple, clear Spanish. "
    "Keep responses short (1-2 sentences). If the user makes a major mistake, "
    "briefly correct them in English in brackets, then wait for their next attempt. "
    "Only offer and confirm items from this menu:\n\n" + MENU
)

GREETING_TEXT = "¡Hola! Bienvenido a nuestro bar de tapas. ¿Qué le gustaría pedir hoy?"

st.set_page_config(page_title="Spanish Waiter", page_icon="🍷")
st.title("🍷 Practica tu español - Tapas Bar Madrid")

with st.sidebar:
    st.header("Menú")
    st.markdown(MENU)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": GREETING_TEXT}]
if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = None
if "last_played_index" not in st.session_state:
    st.session_state.last_played_index = -1


def strip_markdown(text):
    return re.sub(r"[*_`]", "", text)


def speech_widget(text, autoplay):
    text_js = json.dumps(strip_markdown(text))
    autoplay_js = "speak();" if autoplay else ""
    html = f"""
    <button onclick="speak()" style="padding:4px 10px;border-radius:6px;
        border:1px solid #999;cursor:pointer;background:#fff;">
      ▶ Escuchar de nuevo
    </button>
    <script>
      function speak() {{
        const utter = new SpeechSynthesisUtterance({text_js});
        utter.lang = "es-ES";
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
      }}
      {autoplay_js}
    </script>
    """
    components.html(html, height=40)


def transcribe(wav_bytes):
    buf = io.BytesIO(wav_bytes)
    buf.name = "audio.wav"
    transcript = client.audio.transcriptions.create(
        model="whisper-1", file=buf, language="es"
    )
    return transcript.text


def get_reply(history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]
    response = client.chat.completions.create(model=LLM_MODEL, messages=messages)
    return response.choices[0].message.content


last_index = len(st.session_state.messages) - 1
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant":
            should_autoplay = i == last_index and i > st.session_state.last_played_index
            if should_autoplay:
                st.session_state.last_played_index = i
            speech_widget(msg["content"], should_autoplay)

audio_segment = audiorecorder("Click to record", "Click to stop")

if len(audio_segment) > 0:
    buf = io.BytesIO()
    audio_segment.export(buf, format="wav")
    wav_bytes = buf.getvalue()
    audio_hash = hashlib.md5(wav_bytes).hexdigest()

    if audio_hash != st.session_state.last_audio_hash:
        st.session_state.last_audio_hash = audio_hash
        with st.spinner("Escuchando..."):
            user_text = transcribe(wav_bytes).strip()
        if user_text:
            st.session_state.messages.append({"role": "user", "content": user_text})
            with st.spinner("El camarero esta pensando..."):
                reply_text = get_reply(st.session_state.messages)
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
            st.rerun()
        else:
            st.warning("No pude entender el audio. Intenta grabar de nuevo.")
