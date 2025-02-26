import streamlit as st
import tempfile
import re
import shutil
import os

# IMPORTANT: st.set_page_config MUSS als erstes kommen!
st.set_page_config(page_title="Maxis Hörbuchmaker: Text zu Sprache", page_icon="🔊", layout="centered")

# Versuch, system-weites ffmpeg (und ffprobe) zu nutzen
from pydub import AudioSegment
system_ffmpeg = shutil.which("ffmpeg")
system_ffprobe = shutil.which("ffprobe")
if system_ffmpeg and system_ffprobe:
    AudioSegment.converter = system_ffmpeg
    AudioSegment.ffprobe = system_ffprobe
else:
    # Falls kein system-weites ffmpeg gefunden wurde, versuche imageio-ffmpeg zu nutzen
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        AudioSegment.converter = ffmpeg_path
        # Versuche, den ffprobe-Pfad aus dem ffmpeg-Pfad abzuleiten
        ffprobe_candidate = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if os.path.exists(ffprobe_candidate):
            AudioSegment.ffprobe = ffprobe_candidate
        else:
            st.error("ffprobe wurde nicht gefunden. Bitte stellen Sie sicher, dass ffmpeg (inklusive ffprobe) installiert ist.")
    except ImportError:
        st.error("ffmpeg wurde nicht gefunden. Bitte installieren Sie ffmpeg oder fügen Sie es dem PATH hinzu.")

from openai import OpenAI

# OpenAI API-Schlüssel Setup
# Zugriff auf den API-Schlüssel aus den Streamlit-Secrets
OPENAI_API_KEY = st.secrets["openai"]["api_key"]
# Initialisiere den OpenAI-Client
client = OpenAI(api_key=OPENAI_API_KEY)

MAX_CHARS = 4096  # Maximale Zeichen pro Anfrage (hidden Limit des TTS-Modells)

def text_to_speech(text, voice, model):
    """
    Wandelt einen Text in Sprache um und speichert das Audio in einer temporären MP3-Datei.
    Gibt im Fehlerfall einen String zurück, der mit "Error:" beginnt.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
            temp_file = temp_audio_file.name
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                input=text
            )
            response.stream_to_file(temp_file)
        if not os.path.exists(temp_file):
            return "Error: Temporäre Audio-Datei wurde nicht erstellt: " + temp_file
        return temp_file
    except Exception as e:
        return "Error: " + str(e)

def chunk_text(text, max_length=MAX_CHARS):
    """
    Zerlegt den Text in Stücke mit höchstens max_length Zeichen, behält dabei alle Whitespace-Zeichen.
    """
    tokens = re.split(r'(\s+)', text)
    chunks = []
    current_chunk = ""
    for token in tokens:
        if len(current_chunk) + len(token) <= max_length:
            current_chunk += token
        else:
            chunks.append(current_chunk)
            current_chunk = token
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

def convert_text_to_speech(text, voice, model):
    """
    Teilt den Text in Chunks, falls er zu lang ist, und fügt die resultierenden Audios zusammen.
    Zeigt dabei einen Fortschrittsbalken und Statusmeldungen an.
    """
    if len(text) <= MAX_CHARS:
        return text_to_speech(text, voice, model)
    else:
        chunks = chunk_text(text)
        combined_audio = None
        progress_bar = st.progress(0)
        status = st.empty()
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            status.text(f"Verarbeite Chunk {i+1} von {total}...")
            audio_path = text_to_speech(chunk, voice, model)
            if audio_path.startswith("Error:"):
                st.error(f"Fehler bei Chunk {i+1}: {audio_path}")
                return audio_path
            if not os.path.exists(audio_path):
                st.error(f"Audio-Datei für Chunk {i+1} nicht gefunden: {audio_path}")
                return f"Error: Audio-Datei für Chunk {i+1} nicht gefunden"
            try:
                segment = AudioSegment.from_mp3(audio_path)
            except Exception as ex:
                st.error(f"Fehler beim Laden von Chunk {i+1}: {ex}")
                return f"Error: Fehler beim Laden von Chunk {i+1}: {ex}"
            if combined_audio is None:
                combined_audio = segment
            else:
                combined_audio += segment
            progress_bar.progress((i+1)/total)
        status.text("Alle Chunks verarbeitet, kombiniere Audio...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as out_file:
            combined_audio.export(out_file.name, format="mp3")
            status.text("Audio-Kombination abgeschlossen.")
            return out_file.name

def estimate_price_and_duration(text, rate_per_million):
    """
    Schätzt Kosten und Dauer basierend auf der Zeichenanzahl.
    Dauer: Annahme 0,4 Sekunden pro Wort.
    """
    char_count = len(text)
    estimated_cost = (char_count / 1_000_000) * rate_per_million
    word_count = len(text.split())
    estimated_seconds = word_count * 0.4
    return estimated_cost, estimated_seconds

def format_duration(seconds):
    """
    Formatiert Sekunden in Minuten und Sekunden.
    """
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    if minutes > 0:
        return f"{minutes} Minuten {sec} Sekunden"
    else:
        return f"{sec} Sekunden"

def fix_line_breaks(text):
    """
    Ersetzt einfache Zeilenumbrüche innerhalb eines Absatzes durch Leerzeichen,
    lässt aber doppelte Zeilenumbrüche als Absatztrenner.
    """
    return re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

def correct_direct_text():
    st.session_state.text_input = fix_line_breaks(st.session_state.text_input)

def correct_file_text():
    st.session_state.file_text = fix_line_breaks(st.session_state.file_text)

# --- Layout & UI ---

# Keine Debug-Ausgaben hier – alle Hinweise erscheinen nur in Fehlerfällen.

st.markdown(
    """
    <style>
    .main {background-color: #f5f5f5; padding: 2rem; border-radius: 10px; max-width: 800px; margin: auto;}
    h1 {color: #4A90E2; text-align: center;}
    h2, h3 {color: #333333;}
    .estimate {font-size: 1.2rem; font-weight: bold; margin: 0.5rem 0;}
    </style>
    """,
    unsafe_allow_html=True
)
st.markdown('<div class="main">', unsafe_allow_html=True)
st.title("Maxis Hörbuchmaker: Text zu Sprache")
st.markdown("Diese App wandelt Text in Sprache um – ideal für Hörbücher und mehr.")

# Sprache (nur als Auswahl, wird aktuell nicht an die API weitergegeben)
sprachen = {"Deutsch": "de", "English": "en", "Français": "fr", "Español": "es"}
selected_language = st.selectbox("Wählen Sie die Sprache:", list(sprachen.keys()))

# Modelle (Preisangabe pro 1M Zeichen)
modelle = {
    "TTS Speech generation ($15.00 / 1M characters)": {"model": "tts-1", "rate": 15.00},
    "TTS HD Speech generation ($30.00 / 1M characters)": {"model": "tts-1-hd", "rate": 30.00}
}
selected_model = st.selectbox("Wählen Sie das Modell:", list(modelle.keys()))
rate = modelle[selected_model]["rate"]

# Stimmenauswahl
voices = {
    "Alloy (Neutral)": "alloy",
    "Echo (Männlich)": "echo",
    "Fable (Jugendlich)": "fable",
    "Onyx (Männlich)": "onyx",
    "Nova (Weiblich)": "nova",
    "Shimmer (Weiblich)": "shimmer"
}
selected_voice = st.selectbox("Wählen Sie eine Stimme:", list(voices.keys()))

st.markdown("---")
st.subheader("Direkte Texteingabe")
st.text_area("Geben Sie den Text ein, den Sie umwandeln möchten:", key="text_input", height=150)
st.button("Zeilenumbrüche korrigieren", on_click=correct_direct_text)

if st.button("Text in Sprache umwandeln"):
    if st.session_state.text_input.strip() == "":
        st.warning("Bitte geben Sie einen Text ein.")
    else:
        with st.spinner("Wandle Text in Sprache um..."):
            audio_file_path = convert_text_to_speech(
                st.session_state.text_input,
                voices[selected_voice],
                modelle[selected_model]["model"]
            )
        if isinstance(audio_file_path, str) and audio_file_path.startswith("Error:"):
            st.error(f"Ein Fehler ist aufgetreten: {audio_file_path}")
        else:
            st.success("Umwandlung abgeschlossen!")
            st.audio(audio_file_path, format="audio/mp3")
            with open(audio_file_path, "rb") as file:
                st.download_button(
                    label="Audio-Datei herunterladen",
                    data=file,
                    file_name="tts_output.mp3",
                    mime="audio/mp3"
                )

st.markdown("---")
st.subheader("Datei Upload und Bearbeitung")
uploaded_file = st.file_uploader("Laden Sie eine PDF, EPUB, TXT etc. hoch", type=["pdf", "epub", "txt"])
if uploaded_file is not None:
    file_details = {"Dateiname": uploaded_file.name, "Dateityp": uploaded_file.type, "Größe": uploaded_file.size}
    st.write(file_details)
    extracted_text = ""
    if uploaded_file.type == "application/pdf":
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"
        except Exception as e:
            extracted_text = f"Fehler beim Lesen der PDF: {e}"
    elif uploaded_file.type == "application/epub+zip":
        extracted_text = "EPUB Dateien können aktuell nicht verarbeitet werden."
    else:
        try:
            extracted_text = uploaded_file.read().decode("utf-8")
        except Exception as e:
            extracted_text = f"Fehler beim Lesen der Datei: {e}"
    st.markdown("**Extrahierter Text:**")
    st.text(extracted_text)
    st.text_area("Bearbeiten Sie den extrahierten Text:", value=extracted_text, key="file_text", height=150)
    st.button("Zeilenumbrüche im extrahierten Text korrigieren", on_click=correct_file_text)
    
    estimated_cost, estimated_seconds = estimate_price_and_duration(extracted_text, rate)
    st.markdown(f'<p class="estimate">Geschätzte Dauer: {format_duration(estimated_seconds)}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="estimate">Geschätzte Kosten: ${estimated_cost:.2f}</p>', unsafe_allow_html=True)
    
    if st.button("Preis bestätigen und TTS starten"):
        if st.session_state.file_text.strip() == "":
            st.warning("Bitte bearbeiten Sie den Text oder laden Sie eine gültige Datei hoch.")
        else:
            with st.spinner("Wandle Datei-Text in Sprache um..."):
                audio_file_path = convert_text_to_speech(
                    st.session_state.file_text,
                    voices[selected_voice],
                    modelle[selected_model]["model"]
                )
            if isinstance(audio_file_path, str) and audio_file_path.startswith("Error:"):
                st.error(f"Ein Fehler ist aufgetreten: {audio_file_path}")
            else:
                st.success("Umwandlung abgeschlossen!")
                st.audio(audio_file_path, format="audio/mp3")
                with open(audio_file_path, "rb") as file:
                    st.download_button(
                        label="Audio-Datei herunterladen",
                        data=file,
                        file_name="tts_output.mp3",
                        mime="audio/mp3"
                    )

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("Erstellt mit ❤️ unter Verwendung von Streamlit und dem OpenAI TTS-Modell")
