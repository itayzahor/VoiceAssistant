# Tapas Bar Madrid — a voice assistant for practicing Spanish

A voice-based conversation partner for **one specific learner**: an English speaker at
**A2 (CEFR elementary) Spanish**, practicing a single real-world scenario — ordering food
at a tapas bar in Madrid. You talk to a waiter by voice, he replies in simple spoken
Spanish, and you keep the conversation going until you've ordered and asked for the bill.

## What it looks like

An illustrated restaurant scene (you, seated at a table; the waiter, standing) is the
main interface. The waiter's replies appear in a speech bubble above his head and are
spoken aloud; you reply by holding down a "press to speak" button. A short narrated
intro sets the scene before you start.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (needs a funded/billed OpenAI
   account — the free trial tier is not enough to run this reliably; see "Known
   limitations" below for why).
3. `ffmpeg`/`ffprobe` are fetched automatically at first run via the `static-ffmpeg`
   package — no manual install needed.
4. `streamlit run app.py`, then open the local URL it prints.

Use a browser with decent Web Speech API voice support — Chrome on Windows/Mac is the
best-tested target.

## Architecture

- **STT**: OpenAI Whisper (`whisper-1`), given `language="es"` since the browser mic
  captures Spanish speech directly.
- **LLM**: `gpt-4o-mini`, given a system prompt that pins the waiter's persona, restricts
  it to A2-level grammar, and grounds it in a fixed menu (see below).
- **TTS**: the browser's own Web Speech API (`SpeechSynthesisUtterance`), not a cloud TTS
  model. Everything — the waiter's voice, the narrator's voice, word-level pronunciation
  on tap — runs client-side, for free, with no extra API calls.
- **UI**: a single `app.py` Streamlit script. The restaurant scene is hand-built inline
  SVG/CSS/JS rendered via `st.components.v1.html`, not an external asset or image
  generator — this keeps it a single dependency-free file and made the animated,
  interactive parts (word tap-to-translate, reading highlight) possible without a JS
  build step.
- **State**: in-memory `st.session_state` only, per the assignment's scope — no database,
  no accounts, nothing persists across a page refresh.

## Decisions that mattered

**Grounding the menu explicitly.** Early on, the waiter would improvise dish names when
asked "what do you have?", which broke immersion and made the conversation short. Adding
a real five-category menu (tapas fría/caliente, chef's specials, desserts, drinks) to the
system prompt fixed this and, as a side effect, gave the conversation somewhere to go —
starters → a specials question → dessert → drinks — which matters for an app whose whole
point is getting the learner to produce more Spanish, not less.

**A2 grammar is enforced explicitly, not just implied by "keep it simple."** The system
prompt explicitly bans subjunctive, compound/perfect, and conditional tenses, restricting
the waiter to present tense and simple near-future ("voy a..."). Without this, GPT-4o-mini
would drift into more natural but grammatically advanced Spanish that an actual A2 learner
wouldn't be ready for.

**No error correction, by design (this changed mid-build).** The first version had the
waiter flag major mistakes with a bracketed English note. In practice this became more
confusing than helpful: Whisper's transcription of A2-level (sometimes mispronounced)
Spanish isn't always accurate, so "corrections" were frequently correcting a transcription
error, not a real mistake the learner made. Given STT is the weak link here, the waiter
now always responds naturally to what it thinks was meant and never corrects — a real
tradeoff (an app literally about learning a language stopped doing explicit teaching of
mistakes), decided by prioritizing not-annoying over pedagogically maximal.

**TTS moved off a cloud model to the browser, out of necessity.** The original plan (see
scope note below) hit a hard 10-request/day quota on a cloud TTS model — nowhere near
enough for iterative testing, let alone real use. Rebuilding TTS on the Web Speech API
removed that ceiling entirely (free, unlimited, client-side) and, as a side effect, made
word-level tap-to-hear-pronunciation trivial to add later, since there's no per-request
cost to worry about.

**Comprehension support is layered, not single-mode.** A2 learners need help at two
different levels that don't substitute for each other: individual **words** (tap any word
in the waiter's bubble for a quick meaning + pronunciation, without seeing the whole
sentence's meaning) and the **whole sentence** (a separate "Translate" button, for when
word-order or a construction like "voy a" doesn't click from vocabulary alone). Word
translations are pre-fetched the moment a reply arrives so tapping is instant.

**Reading-highlight timing is estimated, not measured.** The Web Speech API's real
word-boundary events (`onboundary`) turned out to be unreliable across voices/browsers in
testing — highlighting would jump to "all done" at the end instead of tracking speech.
The fix was to stop relying on that event and instead schedule each word's highlight on a
timer, sized proportionally from the text length. It's an approximation (tuned to roughly
match the chosen speech rate), not exact synchronization, but it's consistent everywhere
instead of working on some machines and not others.

## What was cut

Per the assignment's scope guidance:

- **No database, no accounts, no persistence** — conversation lives in `st.session_state`
  and is gone on refresh.
- **No streaming audio** — push-to-talk (record, then stop, then it processes) rather than
  a live audio stream.
- **One language, one learner profile, one scenario** — hardcoded to A2 Spanish /
  restaurant ordering. See below for what changing this would involve.
- **No user accounts, no progress tracking, no vocabulary spaced-repetition** — this is a
  single-session conversation practice tool, not a full course product.
- **No deployment** — runs locally via `streamlit run app.py`; nothing is hosted.

## Known limitations

- **A brief flash on each turn.** The scene is rendered via `st.components.v1.html`
  (an embedded iframe), which reloads when its content changes — each new reply causes a
  short repaint. I made two rounds of CSS fixes to soften it (matching the iframe's
  background color so the gap isn't a stark black flash) but didn't fully eliminate it.
  A fully seamless in-place update would require building a real custom Streamlit
  component (a React + build-tooling project), which was out of scope here.
- **Voice selection is best-effort.** Which Spanish/English voices exist depends entirely
  on the user's browser/OS. The code tries to pick a female voice for the narrator and a
  distinct one for the waiter (by name heuristics, then by locale, then by pitch-shifting
  as a last-resort guarantee of audible difference) — but the actual voice quality and
  availability isn't something the app controls.
- **STT accuracy drives conversation quality.** Since corrections were removed specifically
  because of transcription noise, the whole experience is only as good as Whisper's read
  of the learner's Spanish.

## What would change for a different learner

The things that are hardcoded and would need to change:

- **`SYSTEM_PROMPT`'s language and CEFR constraints** — both the target language and the
  specific grammar/vocabulary ceiling (e.g., a B1 learner should *not* have subjunctive
  banned; a different language needs entirely different grammar guardrails, not just a
  translated prompt).
- **`MENU` and the scenario itself** — ordering at a restaurant was chosen because it's a
  bounded, real-world task with a natural conversational arc (greeting → order → specials →
  dessert → bill). A different scenario (e.g., checking into a hotel, asking for
  directions) would need its own grounding content, not just a reused menu structure.
- **STT language hint** (`language="es"` in the Whisper call) and the **TTS voice locale
  preferences** (currently `es-ES`/`es-US`) would need to match the new target language —
  and voice availability/quality varies a lot by language in the Web Speech API, so this
  is worth checking early for a new language, not assumed to work the same as Spanish did.
- **The illustrated scene's language-agnostic; only the "waiter" framing would need to
  change** if the scenario moves away from a restaurant (e.g., a hotel scene would need a
  receptionist character instead).
