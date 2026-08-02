import hashlib
import io
import json
import os
import re
import time

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

MENU = """**Tapas frías**
- Jamón ibérico - 8,00€
- Queso manchego - 6,50€
- Ensaladilla rusa - 4,50€
- Boquerones en vinagre - 5,50€
- Pan con tomate - 3,00€
- Aceitunas - 2,50€

**Tapas calientes**
- Patatas bravas - 4,50€
- Tortilla española - 5,00€
- Croquetas de jamón - 6,00€
- Gambas al ajillo - 7,50€
- Pimientos de Padrón - 5,00€
- Calamares fritos - 8,00€

**Especialidades del chef**
- Paella mixta (para compartir) - 14,00€
- Pulpo a la gallega - 12,50€
- Solomillo al whisky - 13,00€

**Postres**
- Flan casero - 4,00€
- Tarta de Santiago - 5,00€
- Churros con chocolate - 5,50€
- Crema catalana - 4,50€

**Bebidas**
- Agua - 1,50€
- Vino tinto / blanco / rosado - 3,00€
- Cerveza - 2,50€
- Tinto de verano - 3,50€
- Sangría - 4,00€
- Café solo / con leche - 1,80€"""

SYSTEM_PROMPT = (
    "You are a friendly waiter at a tapas bar in Madrid. The user is an A2 "
    "(CEFR elementary) Spanish learner trying to order food. Respond in simple, "
    "clear Spanish strictly at A2 grammar level: use only present tense and "
    "simple near-future ('voy a...'), never the subjunctive mood, never "
    "compound/perfect or conditional tenses, and avoid idioms. Use common, "
    "everyday vocabulary only. Keep responses short (1-2 sentences). Do not "
    "correct the user's grammar, vocabulary, or pronunciation — just respond "
    "naturally to what they most likely meant, since the speech transcription "
    "is sometimes imperfect and treating it as a mistake would often be wrong. "
    "If asked about specials or recommendations, enthusiastically highlight items "
    "from 'Especialidades del chef'. Before bringing the bill, if the guest hasn't "
    "mentioned dessert, ask if they'd like to see the postres. "
    "Only offer and confirm items from this menu:\n\n" + MENU
)

GREETING_TEXT = "¡Hola! Bienvenido a nuestro bar de tapas. ¿Qué le gustaría pedir hoy?"

NARRATION_TEXT = (
    "¡Bienvenido a Madrid! Es una tarde soleada y estás en un bar de tapas "
    "muy famoso. Te sientas en una mesa cerca de la ventana. El camarero se "
    "acerca a tu mesa con una gran sonrisa. ¡Vamos a pedir la comida!"
)

NARRATION_TEXT_EN = (
    "Welcome to Madrid! It's a sunny afternoon and you're at a very famous "
    "tapas bar. You sit at a table near the window. The waiter approaches "
    "your table with a big smile. Let's order some food!"
)

st.set_page_config(page_title="Tapas Bar Madrid", page_icon="🍷")
st.title("🍷 Tapas Bar Madrid")

st.markdown(
    """
    <style>
      iframe[height="460"] { background-color: #E8A87C !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Menu")
    st.markdown(MENU)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": GREETING_TEXT}]
if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = None
if "processing" not in st.session_state:
    st.session_state.processing = False
if "pending_audio" not in st.session_state:
    st.session_state.pending_audio = None
if "transcription_error" not in st.session_state:
    st.session_state.transcription_error = False
if "last_played_index" not in st.session_state:
    st.session_state.last_played_index = -1
if "started" not in st.session_state:
    st.session_state.started = False
if "translations" not in st.session_state:
    st.session_state.translations = {}
if "translation_visible" not in st.session_state:
    st.session_state.translation_visible = False
if "word_translations" not in st.session_state:
    st.session_state.word_translations = {}


def strip_markdown(text):
    return re.sub(r"[*_`]", "", text)


def translate_words(text):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "Given a Spanish sentence, return a JSON object mapping "
                "each distinct word in it (lowercase, punctuation stripped, accents "
                'kept) to its short English translation. Format: {"word": "translation"}. '
                "Skip punctuation-only tokens.",
            },
            {"role": "user", "content": text},
        ],
    )
    return json.loads(response.choices[0].message.content)


SCENE_TEMPLATE = r"""
<style>
  html, body {
    margin: 0;
    background: #E8A87C;
  }
  .scene-wrap {
    position: relative;
    width: 100%;
    height: 440px;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 6px 18px rgba(0,0,0,0.18);
    background: #E8A87C;
  }
  .scene-wrap svg { display: block; width: 100%; height: 100%; }

  .bob-waiter { animation: bob 2.6s ease-in-out infinite; }
  .bob-user { animation: bob 3.1s ease-in-out infinite; animation-delay: .4s; }
  @keyframes bob {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-7px); }
  }

  .eyes { transform-box: fill-box; transform-origin: center; animation: blink 4.6s infinite; }
  .eyes-user { animation-delay: 1.4s; }
  @keyframes blink {
    0%, 94%, 100% { transform: scaleY(1); }
    97% { transform: scaleY(0.12); }
  }

  .bubble {
    box-sizing: border-box;
    position: relative;
    background: #ffffff;
    border: 3px solid #2b2b2b;
    border-radius: 20px;
    padding: 14px 16px;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.3;
    color: #2b2b2b;
    opacity: 0;
    transform: scale(.6);
    box-shadow: 0 4px 0 rgba(0,0,0,0.08);
    overflow: visible;
  }
  .bubble-waiter {
    font-size: 18px;
    line-height: 2.4;
  }
  .bubble.show { animation: pop .35s ease-out forwards; }
  @keyframes pop {
    0% { opacity: 0; transform: scale(.6); }
    65% { opacity: 1; transform: scale(1.06); }
    100% { opacity: 1; transform: scale(1); }
  }
  .bubble:after {
    content: "";
    position: absolute;
    bottom: -13px;
    left: 34px;
    width: 20px;
    height: 20px;
    background: #ffffff;
    border-right: 3px solid #2b2b2b;
    border-bottom: 3px solid #2b2b2b;
    transform: rotate(45deg);
  }
  .bubble-user:after { left: auto; right: 34px; }

  .replay-btn {
    position: absolute;
    top: -10px;
    right: -10px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: 2px solid #2b2b2b;
    background: #fff;
    font-size: 15px;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .translation-line {
    display: none;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed #999;
    font-style: italic;
    font-weight: 400;
    font-size: 13px;
    color: #555;
  }
  .translation-line.show { display: block; }

  .word {
    position: relative;
    border-radius: 4px;
    padding: 1px 3px;
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease;
  }
  .word.read {
    background-color: #a9e8b8;
    color: #14532d;
    font-weight: 700;
  }
  .word-tip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 4px;
    background: #fff8dc;
    border: 2px solid #d4a017;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 600;
    color: #6b4f00;
    white-space: nowrap;
    z-index: 30;
  }
</style>

<div class="scene-wrap">
<svg viewBox="0 0 900 500" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="wallGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#EFB48A"/>
      <stop offset="100%" stop-color="#D98E5D"/>
    </linearGradient>
    <linearGradient id="floorGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#8B5E3C"/>
      <stop offset="100%" stop-color="#6F4A2E"/>
    </linearGradient>
    <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#CDEEFB"/>
      <stop offset="100%" stop-color="#EAF9FD"/>
    </linearGradient>
    <pattern id="checker" width="40" height="40" patternUnits="userSpaceOnUse">
      <rect width="40" height="40" fill="#F4E9DC"/>
      <rect width="20" height="20" fill="#D1524B"/>
      <rect x="20" y="20" width="20" height="20" fill="#D1524B"/>
    </pattern>
  </defs>

  <rect x="0" y="0" width="900" height="330" fill="url(#wallGrad)"/>
  <rect x="0" y="330" width="900" height="170" fill="url(#floorGrad)"/>
  <g stroke="#5A3B25" stroke-width="2" opacity="0.35">
    <line x1="90" y1="330" x2="90" y2="500"/>
    <line x1="220" y1="330" x2="220" y2="500"/>
    <line x1="350" y1="330" x2="350" y2="500"/>
    <line x1="480" y1="330" x2="480" y2="500"/>
    <line x1="610" y1="330" x2="610" y2="500"/>
    <line x1="740" y1="330" x2="740" y2="500"/>
    <line x1="870" y1="330" x2="870" y2="500"/>
  </g>

  <path d="M0,30 Q225,68 450,30 T900,30" fill="none" stroke="#5A3B25" stroke-width="3" opacity="0.5"/>
  <g fill="#FFD166">
    <circle cx="0" cy="30" r="8"/><circle cx="150" cy="45" r="8"/><circle cx="300" cy="38" r="8"/>
    <circle cx="450" cy="30" r="8"/><circle cx="600" cy="38" r="8"/><circle cx="750" cy="45" r="8"/><circle cx="900" cy="30" r="8"/>
  </g>

  <rect x="55" y="45" width="150" height="170" rx="14" fill="#6F4A2E"/>
  <rect x="65" y="55" width="130" height="150" rx="10" fill="url(#skyGrad)"/>
  <rect x="60" y="125" width="140" height="8" fill="#6F4A2E"/>
  <rect x="126" y="55" width="8" height="150" fill="#6F4A2E"/>
  <circle cx="165" cy="80" r="14" fill="#FFDE7A"/>
  <path d="M75,200 L100,150 L115,175 L140,140 L165,200 Z" fill="#8FA6B2" opacity="0.8"/>

  <ellipse cx="90" cy="470" rx="55" ry="16" fill="#6F4A2E"/>
  <rect x="75" y="440" width="30" height="35" rx="6" fill="#B5651D"/>
  <g fill="#3F7F52">
    <ellipse cx="90" cy="420" rx="26" ry="18" transform="rotate(-15 90 420)"/>
    <ellipse cx="75" cy="435" rx="20" ry="14" transform="rotate(20 75 435)"/>
    <ellipse cx="108" cy="435" rx="20" ry="14" transform="rotate(-25 108 435)"/>
  </g>

  <!-- user (seated) -->
  <g class="bob-user">
    <ellipse cx="280" cy="420" rx="55" ry="16" fill="#2b2b2b" opacity="0.15"/>
    <rect x="238" y="345" width="30" height="55" rx="12" fill="#E8B08A"/>
    <rect x="292" y="345" width="30" height="55" rx="12" fill="#E8B08A"/>
    <rect x="228" y="330" width="104" height="95" rx="26" fill="#3AAFA9"/>
    <circle cx="280" cy="300" r="32" fill="#E8B08A"/>
    <path d="M248,290 Q248,254 280,254 Q312,254 312,290 Q296,270 280,272 Q264,270 248,290 Z" fill="#5A3A2E"/>
    <g class="eyes eyes-user" fill="#2b2b2b">
      <circle cx="269" cy="302" r="4"/>
      <circle cx="291" cy="302" r="4"/>
    </g>
    <path d="M267,315 Q280,324 293,315" fill="none" stroke="#2b2b2b" stroke-width="3" stroke-linecap="round"/>
  </g>

  <!-- table -->
  <ellipse cx="450" cy="440" rx="230" ry="55" fill="url(#checker)" stroke="#3E2B1F" stroke-width="4"/>
  <rect x="443" y="398" width="10" height="30" rx="3" fill="#F4E7C1"/>
  <path d="M448,398 Q444,388 448,380 Q452,388 448,398 Z" fill="#F2A93B"/>
  <circle cx="540" cy="422" r="20" fill="#FFFFFF" stroke="#CFCFCF" stroke-width="2"/>
  <ellipse cx="533" cy="418" rx="6" ry="4" fill="#C97B4A"/>
  <ellipse cx="546" cy="420" rx="6" ry="4" fill="#7A9D54"/>
  <ellipse cx="540" cy="428" rx="6" ry="4" fill="#C0392B"/>

  <!-- waiter (standing) -->
  <g class="bob-waiter">
    <ellipse cx="690" cy="478" rx="60" ry="14" fill="#2b2b2b" opacity="0.15"/>
    <rect x="660" y="415" width="22" height="75" rx="9" fill="#2E3A59"/>
    <rect x="700" y="415" width="22" height="75" rx="9" fill="#2E3A59"/>
    <ellipse cx="671" cy="492" rx="16" ry="8" fill="#1B1B1B"/>
    <ellipse cx="711" cy="492" rx="16" ry="8" fill="#1B1B1B"/>
    <rect x="640" y="330" width="100" height="100" rx="22" fill="#FFFFFF"/>
    <path d="M650,340 L690,330 L730,340 L730,425 L650,425 Z" fill="#C97B4A"/>
    <line x1="660" y1="335" x2="678" y2="360" stroke="#C97B4A" stroke-width="7"/>
    <line x1="720" y1="335" x2="702" y2="360" stroke="#C97B4A" stroke-width="7"/>
    <path d="M678,332 L690,344 L702,332 L690,326 Z" fill="#7A1E1E"/>
    <rect x="614" y="338" width="20" height="66" rx="10" fill="#FFFFFF"/>
    <circle cx="624" cy="410" r="12" fill="#F2C29B"/>
    <path d="M726,336 Q764,336 776,352 L744,378 Q726,362 726,336 Z" fill="#FFFFFF"/>
    <circle cx="778" cy="356" r="13" fill="#F2C29B"/>
    <ellipse cx="800" cy="345" rx="42" ry="11" fill="#D8C6A8" stroke="#3E2B1F" stroke-width="2" transform="rotate(-18 800 345)"/>
    <circle cx="690" cy="298" r="34" fill="#F2C29B"/>
    <path d="M656,286 Q656,248 690,248 Q724,248 724,286 Q706,262 690,265 Q674,262 656,286 Z" fill="#2E2320"/>
    <g class="eyes" fill="#2b2b2b">
      <circle cx="678" cy="300" r="4.2"/>
      <circle cx="702" cy="300" r="4.2"/>
    </g>
    <path d="M672,320 Q690,300 708,320" fill="none" stroke="#5C3A1E" stroke-width="4" stroke-linecap="round"/>
    <path d="M675,316 Q690,326 705,316" fill="none" stroke="#2b2b2b" stroke-width="3" stroke-linecap="round"/>
  </g>

  <foreignObject x="430" y="45" width="340" height="260" overflow="visible">
    <div xmlns="http://www.w3.org/1999/xhtml" id="waiterBubble" class="bubble bubble-waiter">
      <button class="replay-btn" onclick="speakWaiter()" title="Play again">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#2b2b2b"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 3-6.7"/>
          <polyline points="3 3 3 8 8 8"/>
        </svg>
      </button>
      <span id="waiterBubbleText"></span>
      <div id="waiterBubbleTranslation" class="translation-line"></div>
    </div>
  </foreignObject>

  <foreignObject x="150" y="90" width="260" height="150">
    <div xmlns="http://www.w3.org/1999/xhtml" id="userBubble" class="bubble bubble-user">
      <span id="userBubbleText"></span>
    </div>
  </foreignObject>
</svg>
</div>

<script>
(function() {
  var waiterText = '';
  var userText = '';
  var wordTranslations = {};

  var waiterBubble = document.getElementById('waiterBubble');
  var userBubble = document.getElementById('userBubble');
  var translationEl = document.getElementById('waiterBubbleTranslation');
  var waiterTextEl = document.getElementById('waiterBubbleText');
  var userTextEl = document.getElementById('userBubbleText');
  var wordBoundaries = [];
  var activeTip = null;

  function normalizeWord(token) {
    return token.toLowerCase().replace(/^[^a-zà-ÿ0-9]+|[^a-zà-ÿ0-9]+$/gi, '');
  }

  function onWordClick(span, token) {
    var norm = normalizeWord(token);
    var meaning = wordTranslations[norm];
    if (!meaning) return;

    var existingTip = span.querySelector('.word-tip');
    if (existingTip) {
      existingTip.remove();
      if (activeTip === existingTip) { activeTip = null; }
      return;
    }

    if (activeTip) { activeTip.remove(); activeTip = null; }

    var tip = document.createElement('div');
    tip.className = 'word-tip';
    tip.textContent = meaning;
    span.appendChild(tip);
    activeTip = tip;

    var wordUtter = new SpeechSynthesisUtterance(norm);
    wordUtter.lang = "es-ES";
    wordUtter.rate = 0.85;
    wordUtter.pitch = 0.8;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(wordUtter);
  }

  function renderWords(text) {
    waiterTextEl.innerHTML = '';
    wordBoundaries = [];
    activeTip = null;
    var tokens = text.split(/(\s+)/);
    var cumulative = 0;
    tokens.forEach(function(token) {
      if (token.length === 0) return;
      if (/\S/.test(token)) {
        var span = document.createElement('span');
        span.className = 'word';
        span.textContent = token;
        span.addEventListener('click', function() { onWordClick(span, token); });
        waiterTextEl.appendChild(span);
        wordBoundaries.push({ start: cumulative, span: span });
      } else {
        waiterTextEl.appendChild(document.createTextNode(token));
      }
      cumulative += token.length;
    });
  }

  var pendingHighlights = [];

  function clearPendingHighlights() {
    pendingHighlights.forEach(function(id) { clearTimeout(id); });
    pendingHighlights = [];
  }

  function pickVoice(langPrefix, genderHint, preferLocale) {
    var voices = window.speechSynthesis.getVoices().filter(function(v) {
      return v.lang.toLowerCase().indexOf(langPrefix) === 0;
    });
    if (voices.length === 0) return null;
    var hints = genderHint === 'female'
      ? ['female', 'helena', 'sabina', 'elena', 'monica', 'paulina', 'zira', 'samantha']
      : genderHint === 'male'
      ? ['male', 'pablo', 'diego', 'jorge', 'raul', 'carlos', 'miguel', 'david', 'george']
      : null;
    if (hints) {
      var match = voices.find(function(v) {
        var n = v.name.toLowerCase();
        return hints.some(function(h) { return n.indexOf(h) !== -1; });
      });
      if (match) return match;
    }
    if (preferLocale) {
      var localeMatch = voices.find(function(v) { return v.lang.toLowerCase() === preferLocale; });
      if (localeMatch) return localeMatch;
    }
    return voices[0];
  }

  function parseSegments(text) {
    var segments = [];
    var regex = /\[([^\]]*)\]/g;
    var lastIndex = 0;
    var match;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        segments.push({ text: text.slice(lastIndex, match.index), lang: 'es-ES', start: lastIndex });
      }
      segments.push({ text: match[1], lang: 'en-US', start: match.index + 1 });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < text.length) {
      segments.push({ text: text.slice(lastIndex), lang: 'es-ES', start: lastIndex });
    }
    return segments;
  }

  function getVoicesReady(callback) {
    var voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) { callback(); return; }
    var called = false;
    window.speechSynthesis.onvoiceschanged = function() {
      if (called) return;
      called = true;
      callback();
    };
    setTimeout(function() { if (!called) { called = true; callback(); } }, 1000);
  }

  function doSpeakWaiter() {
    if (!waiterText) return;
    clearPendingHighlights();
    if (activeTip) { activeTip.remove(); activeTip = null; }
    wordBoundaries.forEach(function(b) { b.span.classList.remove('read'); });

    var segments = parseSegments(waiterText);
    var charsPerSecond = 11;
    var cumulativeMs = 0;

    segments.forEach(function(seg) {
      var segChars = seg.text.length || 1;
      var segDurationMs = Math.max(200, (segChars / charsPerSecond) * 1000);
      wordBoundaries.forEach(function(b) {
        var wordEndChar = b.start + b.span.textContent.length;
        if (wordEndChar > seg.start && wordEndChar <= seg.start + segChars) {
          var localOffset = wordEndChar - seg.start;
          var t = cumulativeMs + (localOffset / segChars) * segDurationMs;
          var id = setTimeout(function() { b.span.classList.add('read'); }, t);
          pendingHighlights.push(id);
        }
      });
      cumulativeMs += segDurationMs;
    });

    function speakSegment(i) {
      if (i >= segments.length) {
        clearPendingHighlights();
        wordBoundaries.forEach(function(b) { b.span.classList.add('read'); });
        return;
      }
      var seg = segments[i];
      if (!seg.text.trim()) { speakSegment(i + 1); return; }
      var utter = new SpeechSynthesisUtterance(seg.text);
      utter.lang = seg.lang;
      utter.rate = 0.85;
      utter.pitch = 0.8;
      var voice = seg.lang === 'es-ES' ? pickVoice('es', 'male', 'es-es') : pickVoice('en', null, null);
      if (voice) { utter.voice = voice; }
      utter.onend = function() { speakSegment(i + 1); };
      window.speechSynthesis.speak(utter);
    }

    window.speechSynthesis.cancel();
    speakSegment(0);
  }

  window.speakWaiter = function() {
    getVoicesReady(doSpeakWaiter);
  };

  var lastAppliedWaiterText = null;

  function applyState(state) {
    waiterText = state.waiterText || '';
    userText = state.userText || '';
    wordTranslations = state.wordTranslations || {};

    if (state.translation) {
      translationEl.textContent = state.translation;
      translationEl.classList.add('show');
    } else {
      translationEl.classList.remove('show');
    }

    var isNewText = waiterText !== lastAppliedWaiterText;
    lastAppliedWaiterText = waiterText;

    if (waiterText) {
      renderWords(waiterText);
      waiterBubble.classList.add('show');
      if (state.autoplay && isNewText) { window.speakWaiter(); }
    } else {
      waiterBubble.classList.remove('show');
    }

    if (userText) {
      userTextEl.textContent = userText;
      userBubble.classList.add('show');
    } else {
      userBubble.classList.remove('show');
    }
  }

  applyState({
    waiterText: __WAITER_TEXT__,
    userText: __USER_TEXT__,
    autoplay: __AUTOPLAY__,
    translation: __TRANSLATION__,
    wordTranslations: __WORD_TRANSLATIONS__
  });
})();
</script>
"""


def scene_widget(waiter_text, user_text, autoplay, translation=None, word_translations=None):
    html = SCENE_TEMPLATE.replace("__WAITER_TEXT__", json.dumps(waiter_text or ""))
    html = html.replace("__USER_TEXT__", json.dumps(user_text or ""))
    html = html.replace("__AUTOPLAY__", json.dumps(bool(autoplay)))
    html = html.replace("__TRANSLATION__", json.dumps(translation or ""))
    html = html.replace("__WORD_TRANSLATIONS__", json.dumps(word_translations or {}))
    components.html(html, height=460)


def loading_button_widget():
    st.button("⏳ Processing...", disabled=True, key="processing_indicator")


def speech_widget(text, autoplay, word_translations=None):
    text_js = json.dumps(strip_markdown(text))
    word_translations_js = json.dumps(word_translations or {})
    html = rf"""
    <script>
      var boundaries = [];
      var textEl = null;
      var pendingHighlights = [];
      var targetText = {text_js};
      var wordTranslations = {word_translations_js};
      var activeTip = null;

      function normalizeWord(token) {{
        return token.toLowerCase().replace(/^[^a-zà-ÿ0-9]+|[^a-zà-ÿ0-9]+$/gi, '');
      }}

      function onWordClick(doc, span, token) {{
        var norm = normalizeWord(token);
        var meaning = wordTranslations[norm];
        if (!meaning) return;

        var existingTip = span.querySelector('.word-tip');
        if (existingTip) {{
          existingTip.remove();
          if (activeTip === existingTip) {{ activeTip = null; }}
          return;
        }}
        if (activeTip) {{ activeTip.remove(); activeTip = null; }}

        var tip = doc.createElement('div');
        tip.className = 'word-tip';
        tip.textContent = meaning;
        span.appendChild(tip);
        activeTip = tip;

        var wordUtter = new SpeechSynthesisUtterance(norm);
        wordUtter.lang = "es-ES";
        wordUtter.rate = 0.85;
        wordUtter.pitch = 1.3;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(wordUtter);
      }}

      function clearPendingHighlights() {{
        pendingHighlights.forEach(function(id) {{ clearTimeout(id); }});
        pendingHighlights = [];
      }}

      function getVoicesReady(callback) {{
        var voices = window.speechSynthesis.getVoices();
        if (voices.length > 0) {{ callback(); return; }}
        var called = false;
        window.speechSynthesis.onvoiceschanged = function() {{
          if (called) return;
          called = true;
          callback();
        }};
        setTimeout(function() {{ if (!called) {{ called = true; callback(); }} }}, 1000);
      }}

      function speak() {{
        getVoicesReady(doSpeak);
      }}

      function doSpeak() {{
        clearPendingHighlights();
        if (activeTip) {{ activeTip.remove(); activeTip = null; }}
        if (textEl) {{
          boundaries.forEach(function(b) {{ b.span.classList.remove('read'); }});
          var totalChars = targetText.length;
          var charsPerSecond = 11;
          var totalDurationMs = Math.max(500, (totalChars / charsPerSecond) * 1000);
          boundaries.forEach(function(b) {{
            var wordEndChar = b.start + b.span.textContent.length;
            var t = (wordEndChar / totalChars) * totalDurationMs;
            var id = setTimeout(function() {{ b.span.classList.add('read'); }}, t);
            pendingHighlights.push(id);
          }});
        }}
        var utter = new SpeechSynthesisUtterance(targetText);
        utter.lang = "es-ES";
        utter.rate = 0.85;
        utter.pitch = 1.3;
        var voices = window.speechSynthesis.getVoices().filter(function(v) {{
          return v.lang.toLowerCase().indexOf('es') === 0;
        }});
        var femaleHints = ['female', 'helena', 'sabina', 'elena', 'monica', 'paulina', 'zira', 'samantha'];
        var femaleVoice = voices.find(function(v) {{
          var n = v.name.toLowerCase();
          return femaleHints.some(function(h) {{ return n.indexOf(h) !== -1; }});
        }});
        if (!femaleVoice) {{
          femaleVoice = voices.find(function(v) {{ return v.lang.toLowerCase() === 'es-us'; }});
        }}
        if (femaleVoice) {{ utter.voice = femaleVoice; utter.lang = femaleVoice.lang; }}
        else if (voices.length > 0) {{ utter.voice = voices[0]; }}
        utter.onend = function() {{
          clearPendingHighlights();
          boundaries.forEach(function(b) {{ b.span.classList.add('read'); }});
        }};
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
      }}

      try {{
        var doc = window.parent.document;
        var dialog = doc.querySelector('[data-testid="stDialog"]');
        var box = dialog ? dialog.firstElementChild : null;
        if (box) {{
          if (!doc.getElementById('narrationWordStyle')) {{
            var styleTag = doc.createElement('style');
            styleTag.id = 'narrationWordStyle';
            styleTag.textContent = '.word{{position:relative;border-radius:4px;padding:1px 3px;'
              + 'cursor:pointer;transition:background-color .15s ease,color .15s ease;}} '
              + '.word.read{{background-color:#a9e8b8;color:#14532d;font-weight:700;}} '
              + '.word-tip{{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);'
              + 'margin-bottom:4px;background:#fff8dc;border:2px solid #d4a017;border-radius:8px;'
              + 'padding:2px 8px;font-size:12px;font-weight:600;color:#6b4f00;'
              + 'white-space:nowrap;z-index:30;}}';
            doc.head.appendChild(styleTag);
          }}

          var paragraphs = box.querySelectorAll('p');
          for (var i = 0; i < paragraphs.length; i++) {{
            if (paragraphs[i].textContent.trim() === targetText) {{
              textEl = paragraphs[i];
              break;
            }}
          }}
          if (textEl) {{
            textEl.style.fontSize = '18px';
            textEl.style.lineHeight = '2.4';
            textEl.innerHTML = '';
            var tokens = targetText.split(/(\s+)/);
            var cumulative = 0;
            tokens.forEach(function(token) {{
              if (token.length === 0) return;
              if (/\S/.test(token)) {{
                var span = doc.createElement('span');
                span.className = 'word';
                span.textContent = token;
                span.addEventListener('click', function() {{ onWordClick(doc, span, token); }});
                textEl.appendChild(span);
                boundaries.push({{ start: cumulative, span: span }});
              }} else {{
                textEl.appendChild(doc.createTextNode(token));
              }}
              cumulative += token.length;
            }});
          }}

          var existing = doc.getElementById('narrationReplayBtn');
          if (existing) existing.remove();
          var btn = doc.createElement('button');
          btn.id = 'narrationReplayBtn';
          btn.title = 'Play again';
          btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
            + 'stroke="#2b2b2b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 3 3 8 8 8"/></svg>';
          btn.style.cssText = 'position:absolute;top:14px;right:14px;z-index:9999;'
            + 'width:30px;height:30px;border-radius:50%;border:2px solid #2b2b2b;'
            + 'background:#fff;cursor:pointer;display:flex;align-items:center;'
            + 'justify-content:center;padding:0;';
          btn.onclick = speak;
          if (getComputedStyle(box).position === 'static') {{
            box.style.position = 'relative';
          }}
          box.appendChild(btn);
        }}
      }} catch (e) {{}}

      if ({json.dumps(bool(autoplay))}) {{ speak(); }}
    </script>
    """
    components.html(html, height=1)


@st.dialog("Welcome", dismissible=False)
def intro_dialog():
    if "narration_word_translations" not in st.session_state:
        st.session_state.narration_word_translations = translate_words(NARRATION_TEXT)
    st.write(NARRATION_TEXT)
    speech_widget(NARRATION_TEXT, autoplay=True, word_translations=st.session_state.narration_word_translations)
    if "narration_translation_visible" not in st.session_state:
        st.session_state.narration_translation_visible = False
    if st.session_state.narration_translation_visible:
        st.caption(NARRATION_TEXT_EN)

    start_col, _, translate_col = st.columns([2, 3, 2])
    with start_col:
        if st.button("Start"):
            st.session_state.started = True
            st.rerun()
    with translate_col:
        if st.button("Hide translation" if st.session_state.narration_translation_visible else "Translate"):
            st.session_state.narration_translation_visible = not st.session_state.narration_translation_visible
            st.rerun()


if not st.session_state.started:
    intro_dialog()
    st.stop()


def transcribe(wav_bytes):
    buf = io.BytesIO(wav_bytes)
    buf.name = "audio.wav"
    transcript = client.audio.transcriptions.create(
        model="whisper-1", file=buf, language="es"
    )
    return transcript.text


def translate_to_english(text):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Translate the given Spanish text to natural English. "
                "Output only the translation, nothing else.",
            },
            {"role": "user", "content": text},
        ],
    )
    return response.choices[0].message.content


def get_reply(history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]
    response = client.chat.completions.create(model=LLM_MODEL, messages=messages)
    return response.choices[0].message.content


latest_waiter_text = None
latest_user_text = None
for m in reversed(st.session_state.messages):
    if m["role"] == "assistant" and latest_waiter_text is None:
        latest_waiter_text = strip_markdown(m["content"])
    if m["role"] == "user" and latest_user_text is None:
        latest_user_text = strip_markdown(m["content"])
    if latest_waiter_text and latest_user_text:
        break

last_index = len(st.session_state.messages) - 1
is_new_waiter_turn = (
    last_index >= 0
    and st.session_state.messages[last_index]["role"] == "assistant"
    and last_index > st.session_state.last_played_index
)
if is_new_waiter_turn:
    st.session_state.last_played_index = last_index
    st.session_state.translation_visible = False

current_translation = None
if st.session_state.translation_visible and last_index >= 0:
    if last_index not in st.session_state.translations:
        st.session_state.translations[last_index] = translate_to_english(latest_waiter_text)
    current_translation = st.session_state.translations[last_index]

current_word_translations = {}
if last_index >= 0 and st.session_state.messages[last_index]["role"] == "assistant":
    if last_index not in st.session_state.word_translations:
        st.session_state.word_translations[last_index] = translate_words(latest_waiter_text)
    current_word_translations = st.session_state.word_translations[last_index]

scene_widget(
    latest_waiter_text,
    latest_user_text,
    autoplay=is_new_waiter_turn,
    translation=current_translation,
    word_translations=current_word_translations,
)

if is_new_waiter_turn and latest_waiter_text and last_index > 0:
    delay = min(6.0, max(1.5, len(latest_waiter_text) / 13))
    waiting_placeholder = st.empty()
    waiting_placeholder.caption("🎙️ Once the waiter finishes speaking, you can record your reply...")
    time.sleep(delay)
    waiting_placeholder.empty()

mic_col, _, translate_col = st.columns([3, 4, 3])
audio_segment = None
with mic_col:
    if st.session_state.processing:
        loading_button_widget()
    else:
        audio_segment = audiorecorder("🎤 Press to speak", "⏹ Stop")
        if st.session_state.transcription_error:
            st.caption("I couldn't understand the audio. Try again.")
with translate_col:
    if st.button("Hide translation" if st.session_state.translation_visible else "Translate"):
        st.session_state.translation_visible = not st.session_state.translation_visible
        st.rerun()

for msg in st.session_state.messages:
    speaker = "Waiter" if msg["role"] == "assistant" else "You"
    st.markdown(f"**{speaker}:** {msg['content']}")

if st.session_state.processing and st.session_state.pending_audio is not None:
    wav_bytes = st.session_state.pending_audio
    st.session_state.pending_audio = None
    user_text = transcribe(wav_bytes).strip()
    if user_text:
        st.session_state.transcription_error = False
        st.session_state.messages.append({"role": "user", "content": user_text})
        reply_text = get_reply(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": reply_text})
    else:
        st.session_state.transcription_error = True
    st.session_state.processing = False
    st.rerun()
elif audio_segment is not None and len(audio_segment) > 0:
    buf = io.BytesIO()
    audio_segment.export(buf, format="wav")
    wav_bytes = buf.getvalue()
    audio_hash = hashlib.md5(wav_bytes).hexdigest()

    if audio_hash != st.session_state.last_audio_hash:
        st.session_state.last_audio_hash = audio_hash
        st.session_state.pending_audio = wav_bytes
        st.session_state.processing = True
        st.rerun()
