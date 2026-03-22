import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import httpx
from google import genai
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, AudioInterface
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

# ── CLI args ─────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="SafeCall agent")
parser.add_argument("--text", action="store_true", help="Run in text mode (type instead of speak)")
parser.add_argument("--incident-id", required=True, help="Active incident UUID to tie updates to")
parser.add_argument("--token", required=True, help="User JWT for authenticating with Shieldly API")
args = parser.parse_args()

TEXT_MODE = args.text
INCIDENT_ID = args.incident_id
AUTH_TOKEN = args.token


# ── No-op audio interface for text mode ──────────────────────────────────────

class TextAudioInterface(AudioInterface):
    """Dummy audio interface that does nothing — used in text mode."""

    def start(self, input_callback):
        self.input_callback = input_callback

    def stop(self):
        pass

    def output(self, audio: bytes):
        pass  # discard audio output

    def interrupt(self):
        pass

# ── Config ────────────────────────────────────────────────────────────────────

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_AGENT_ID = os.environ["ELEVENLABS_AGENT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SHIELDLY_BASE_URL = os.environ.get("SHIELDLY_BASE_URL", "http://localhost:8000")
DISPATCH_ENDPOINT = f"{SHIELDLY_BASE_URL}/api/v1/safecall/{INCIDENT_ID}/update"
DISPATCH_INTERVAL = int(os.environ.get("SAFECALL_DISPATCH_INTERVAL", "8"))
MAX_AGENT_TURNS = 8   # end session after this many agent responses

# ── Clients ───────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = (
    Path(__file__).parent / "extraction_prompt.txt"
).read_text()

el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ── Transcript buffer ─────────────────────────────────────────────────────────

transcript: list[dict] = []  # {"role": "user"|"agent", "text": str, "ts": str}
session_active = False
agent_turn_count = 0
conversation_ref: Conversation | None = None


def _has_user_input() -> bool:
    """True once the user has sent at least one message."""
    return any(t["role"] == "user" for t in transcript)


def _log(msg: str):
    """Print debug logs — suppressed in text mode for clean output."""
    if not TEXT_MODE:
        print(msg)


def _info_complete(extracted: dict) -> bool:
    """True when we have both a location and a threat description."""
    loc = extracted.get("location", {}).get("described")
    threat = extracted.get("threat", {}).get("description")
    return bool(loc and threat)


def _missing_fields(extracted: dict) -> list[str]:
    """Return a list of important fields we still don't have."""
    missing = []
    if not extracted.get("threat", {}).get("description"):
        missing.append("physical description of the person following/threatening her")
    if not extracted.get("threat", {}).get("behavior"):
        missing.append("what the threatening person is currently doing")
    if not extracted.get("threat", {}).get("vehicle"):
        # only flag if we don't even have a description yet
        pass  # vehicle is nice-to-have, don't push for it early
    return missing


def on_agent_response(text: str):
    global agent_turn_count
    agent_turn_count += 1
    transcript.append({"role": "agent", "text": text, "ts": _now()})
    if TEXT_MODE:
        # Clear the "You: " prompt, print agent response on a clean line
        sys.stdout.write(f"\r\033[KLily: {text}\n")
        sys.stdout.flush()
    else:
        print(f"[agent] (turn {agent_turn_count}/{MAX_AGENT_TURNS}) {text[:100]}")
    if agent_turn_count >= MAX_AGENT_TURNS and conversation_ref:
        print(f"[safecall] Max turns ({MAX_AGENT_TURNS}) reached — ending session.")
        conversation_ref.end_session()


def on_user_transcript(text: str):
    transcript.append({"role": "user", "text": text, "ts": _now()})
    if not TEXT_MODE:
        print(f"[user] {text[:100]}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Extraction ────────────────────────────────────────────────────────────────

def build_transcript_text() -> str:
    return "\n".join(
        f"{t['role'].upper()} [{t['ts']}]: {t['text']}"
        for t in transcript[-30:]  # last 30 turns to keep token usage low
    )


def extract_info() -> dict:
    if not transcript:
        return {}

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Here is the conversation so far:\n\n{build_transcript_text()}\n\nExtract the safety information as JSON.",
        config={"system_instruction": EXTRACTION_SYSTEM_PROMPT},
    )

    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw, "parse_error": True}


# ── Dispatch loop ─────────────────────────────────────────────────────────────

async def dispatch_loop():
    # Wait for at least one user message before running extraction
    while session_active and not _has_user_input():
        await asyncio.sleep(1)

    # Let the agent complete its opening flow (Steps 1-2) undisturbed
    await asyncio.sleep(15)

    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        while session_active:
            await asyncio.sleep(DISPATCH_INTERVAL)
            if not session_active:
                break

            _log(f"[dispatch] Running extraction... (transcript has {len(transcript)} turns)")
            try:
                extracted = extract_info()
            except Exception as e:
                _log(f"[extraction] failed: {e}")
                continue
            if not extracted:
                _log("[extraction] No data extracted (empty transcript?)")
                continue

            _log(f"[extraction] Result: {json.dumps(extracted, indent=2)[:300]}")

            if _info_complete(extracted) and agent_turn_count >= 5 and conversation_ref:
                _log("[safecall] Key info collected — ending session early.")
                conversation_ref.end_session()
                break

            # ── Steer the agent toward missing info (only after opening flow) ──
            if conversation_ref and not extracted.get("parse_error") and agent_turn_count >= 3:
                missing = _missing_fields(extracted)
                if missing:
                    items = "; ".join(missing)
                    steer_hint = (
                        f"[SYSTEM INFO — do NOT repeat this literally] "
                        f"We still need: {items}. "
                        f"Gently steer the conversation to get this info without sounding like an interrogation."
                    )
                    try:
                        conversation_ref.send_contextual_update(steer_hint)
                        _log(f"[steer] Sent steering update — missing: {items}")
                    except RuntimeError:
                        _log("[steer] Session already ended, skipping.")
                        break

            payload = {
                "timestamp": _now(),
                "extracted": extracted,
                "transcript_length": len(transcript),
            }

            try:
                resp = await client.post(
                    DISPATCH_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=4.0,
                )
                _log(f"[dispatch] {resp.status_code} — {payload['timestamp']}")

                # Stop dispatching if the incident has been resolved
                if resp.status_code == 409:
                    _log("[dispatch] Incident resolved — stopping dispatch.")
                    if conversation_ref:
                        conversation_ref.end_session()
                    break
            except Exception as e:
                _log(f"[dispatch] failed: {e}")


# ── Session ───────────────────────────────────────────────────────────────────

async def run_session():
    global session_active, conversation_ref
    session_active = True

    mode_label = "TEXT" if TEXT_MODE else "SPEECH"
    print(f"[safecall] Session starting in {mode_label} mode...")
    print(f"[safecall] Incident: {INCIDENT_ID}")
    print(f"[safecall] Dispatch: {DISPATCH_ENDPOINT}")

    audio_iface = TextAudioInterface() if TEXT_MODE else DefaultAudioInterface()

    conversation = Conversation(
        client=el_client,
        agent_id=ELEVENLABS_AGENT_ID,
        requires_auth=True,
        audio_interface=audio_iface,
        callback_agent_response=on_agent_response,
        callback_user_transcript=on_user_transcript,
        callback_agent_response_correction=lambda original, corrected: print(f"[agent-correction] {corrected[:100]}"),
    )

    conversation_ref = conversation

    # start_session() is non-blocking — it spawns a thread and returns immediately
    conversation.start_session()
    print("[safecall] Conversation thread started. Launching background loops...")

    dispatch_task = asyncio.create_task(dispatch_loop())
    print("[safecall] dispatch_loop task created.")

    if TEXT_MODE:
        print("[safecall] Type your messages below. Press Ctrl+C or type 'quit' to end.\n")

    # In text mode, read stdin in a background thread so we don't block the event loop
    if TEXT_MODE:
        text_input_task = asyncio.create_task(_text_input_loop(conversation))
    else:
        text_input_task = None

    try:
        # Block until the conversation ends (end_session is called)
        print("[safecall] Waiting for session to end...")
        await asyncio.to_thread(conversation.wait_for_session_end)
        print("[safecall] wait_for_session_end returned.")
    finally:
        session_active = False
        if text_input_task:
            text_input_task.cancel()
        print("[safecall] session_active = False, waiting for tasks to finish...")
        await dispatch_task
        print("[safecall] Session ended.")
        print(f"[safecall] Total transcript turns: {len(transcript)}")


async def _text_input_loop(conversation: Conversation):
    """Read lines from stdin and send them to the conversation as user messages."""
    while session_active:
        try:
            line = await asyncio.to_thread(input, "You: ")
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() == "quit":
            print("[safecall] User typed 'quit' — ending session.")
            conversation.end_session()
            break
        on_user_transcript(line)
        conversation.send_user_message(line)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(run_session())
