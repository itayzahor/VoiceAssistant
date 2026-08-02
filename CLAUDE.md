# Project Context
- Goal: A 4-hour take-home assignment to build an MVP voice assistant for an A2 Spanish learner to order at a restaurant.
- Scope cuts: No database, no user accounts, no streaming audio. Do not try to build these. Chat history lives in memory.

# Tech Stack & Guidelines
- Language: Python 3
- UI Framework: Streamlit (use `streamlit-audiorecorder` for the microphone)
- Core APIs: OpenAI (Whisper for STT, GPT-4o-mini for LLM logic, TTS for audio output)
- Execution: Run the app locally with `streamlit run app.py`

# Coding Directives
- Prioritize speed, working functionality, and clean core logic over UI polish.
- Do not add speculative error handling.
- Keep all core logic in a single file (`app.py`) unless it becomes unmanageable.
- Generate code incrementally. Ask for approval before rewriting large blocks.

# Persona System Prompt (For the LLM)
"You are a friendly waiter at a tapas bar in Madrid. The user is an A2 Spanish learner trying to order food. Respond in simple, clear Spanish. Keep responses short (1-2 sentences). If the user makes a major mistake, briefly correct them in English in brackets, then wait for their next attempt."
