import os, uuid, base64
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
from faster_whisper import WhisperModel
import google.generativeai as genai
from gtts import gTTS
from langdetect import detect
from dotenv import load_dotenv
load_dotenv()  # this reads your .env file and sets environment variables

# ---------------- Flask & Socket.IO ----------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret"
# eventlet async mode gives low-latency sockets
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ---------------- Models / Config ----------------
# Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini = genai.GenerativeModel("gemini-1.5-flash")

# Whisper (choose: tiny/base/small/medium/large-v3)
# 'small' works on CPU; use 'tiny' or 'base' for lower latency
whisper = WhisperModel("small", device="cpu", compute_type="int8")

# File paths
AUDIO_DIR = os.path.join("static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

SYSTEM_PROMPT = (
    "You are a friendly, patient EdTech career consultant for India. "
    "Keep replies concise (2–4 sentences) yet informative. "
    "Ask clarifying questions when useful. "
    "Provide concrete details about courses, syllabus, duration, fees, and placement support. "
    "Match the student's language (English or Hindi)."
)

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/static/audio/<path:fname>")
def serve_audio(fname):
    return send_from_directory(AUDIO_DIR, fname)

# ---------------- Socket Handlers ----------------
@socketio.on("connect")
def on_connect():
    emit("server_ready", {"ok": True})

@socketio.on("utterance_blob")
def on_utterance(data):
    """
    Receive one utterance chunk (after client-side silence detection),
    transcribe -> LLM -> TTS -> emit reply (text + audio URL).
    """
    try:
        b64 = data.get("b64")    # base64 without header
        mime = data.get("mime")  # e.g., audio/webm; codecs=opus
        if not b64:
            emit("error", {"msg": "No audio received"})
            return

        ext = "webm" if mime and "webm" in mime else "wav"
        in_name = f"in_{uuid.uuid4().hex}.{ext}"
        in_path = os.path.join(AUDIO_DIR, in_name)

        with open(in_path, "wb") as f:
            f.write(base64.b64decode(b64))

        # ---- 1) STT ----
        # faster-whisper supports webm/ogg/wav/mp3 if ffmpeg is installed.
        segments, info = whisper.transcribe(
            in_path,
            vad_filter=True,     # better utterance trimming
            beam_size=1,         # low latency
            best_of=1
        )
        user_text = "".join(seg.text for seg in segments).strip()
        try:
            os.remove(in_path)
        except Exception:
            pass

        if not user_text:
            emit("partial", {"user_text": "", "ai_text": "", "note": "silence"})
            return

        emit("partial", {"user_text": user_text})

        # ---- 2) LLM (Gemini) ----
        prompt = f"{SYSTEM_PROMPT}\nStudent: {user_text}\nAgent:"
        ai_text = gemini.generate_content(prompt).text

        if not ai_text:
            ai_text = "Sorry, I didn’t catch that. Could you please repeat your question?"

        # ---- 3) TTS (gTTS) ----
        # detect language from AI text (gTTS cannot mix Hinglish well)
        try:
            lang = detect(ai_text)
        except Exception:
            lang = "en"
        if lang not in ("hi", "en"):
            lang = "en"

        out_name = f"reply_{uuid.uuid4().hex}.mp3"
        out_path = os.path.join(AUDIO_DIR, out_name)
        gTTS(ai_text, lang=lang, slow=False).save(out_path)

        # ---- 4) Emit back ----
        emit("ai_reply", {
            "user_text": user_text,
            "ai_text": ai_text,
            "audio_url": f"/static/audio/{out_name}"
        })

    except Exception as e:
        emit("error", {"msg": str(e)})

if __name__ == "__main__":
    # Use eventlet web server for socket performance
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
