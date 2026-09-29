import asyncio
import io
import json
import os
import random
import re
import tempfile
from typing import Dict, List, Optional, Tuple

from pydub import AudioSegment
import edge_tts
import streamlit as st

st.set_page_config(
    page_title="IELTS Natural Conversational TTS Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
    <style>
        .main-header {
            font-size: 2.1rem;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 0.2rem;
        }
        .sub-header {
            font-size: 0.98rem;
            color: #475569;
            margin-bottom: 1.2rem;
        }
        .speaker-badge {
            background-color: #EEF2FF;
            color: #4338CA;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        .narrator-badge {
            background-color: #FEF3C7;
            color: #92400E;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        .pause-badge {
            background-color: #F1F5F9;
            color: #475569;
            border: 1px dashed #94A3B8;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        .line-box {
            background: #F8FAFC;
            border-left: 3px solid #3B82F6;
            padding: 10px 14px;
            margin-bottom: 8px;
            border-radius: 0 6px 6px 0;
            font-size: 0.94rem;
        }
        .pause-box {
            background: #F8FAFC;
            border-left: 3px dashed #94A3B8;
            padding: 8px 14px;
            margin-bottom: 8px;
            border-radius: 0 6px 6px 0;
            font-size: 0.90rem;
            color: #64748B;
        }
        .monologue-badge {
            background-color: #FEF3C7;
            color: #92400E;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.85rem;
        }
    </style>
""", unsafe_allow_html=True)


# Curated Top-Tier Microsoft Neural Voices for Conversational IELTS
CURATED_IELTS_VOICES = {
    # British English (Primary IELTS Accent)
    "en-GB-RyanNeural": {"name": "Ryan (British Male - Friendly & Expressive)", "gender": "Male", "locale": "en-GB"},
    "en-GB-SoniaNeural": {"name": "Sonia (British Female - Crisp & Professional)", "gender": "Female", "locale": "en-GB"},
    "en-GB-ThomasNeural": {"name": "Thomas (British Male - Calm, Academic & Articulate)", "gender": "Male", "locale": "en-GB"},
    "en-GB-MaisieNeural": {"name": "Maisie (British Female - Warm & Casual)", "gender": "Female", "locale": "en-GB"},
    "en-GB-LibbyNeural": {"name": "Libby (British Female - Polite & Gentle)", "gender": "Female", "locale": "en-GB"},

    # Australian English (Key IELTS Section 1 & 3 Accent)
    "en-AU-NatashaNeural": {"name": "Natasha (Australian Female - Natural & Bright)", "gender": "Female", "locale": "en-AU"},
    "en-AU-WilliamMultilingualNeural": {"name": "William (Australian Male - Conversational)", "gender": "Male", "locale": "en-AU"},

    # American & Canadian (International Variety)
    "en-US-JennyNeural": {"name": "Jenny (American Female - Conversational & Natural)", "gender": "Female", "locale": "en-US"},
    "en-US-GuyNeural": {"name": "Guy (American Male - Casual & Expressive)", "gender": "Male", "locale": "en-US"},
    "en-US-AvaMultilingualNeural": {"name": "Ava (American Female - Expressive)", "gender": "Female", "locale": "en-US"},
    "en-US-BrianMultilingualNeural": {"name": "Brian (American Male - Confident & Warm)", "gender": "Male", "locale": "en-US"},
    "en-CA-LiamNeural": {"name": "Liam (Canadian Male - Smooth & Natural)", "gender": "Male", "locale": "en-CA"},
    "en-CA-ClaraNeural": {"name": "Clara (Canadian Female - Clear & Friendly)", "gender": "Female", "locale": "en-CA"},
    "en-NZ-MitchellNeural": {"name": "Mitchell (New Zealand Male - Natural)", "gender": "Male", "locale": "en-NZ"},
    "en-IE-EmilyNeural": {"name": "Emily (Irish Female - Melodic & Warm)", "gender": "Female", "locale": "en-IE"},
}


# Heuristics for auto voice matching
FEMALE_INDICATORS = {
    "ruth", "amber", "sarah", "emma", "jenny", "sonia", "clara", "natasha", "lucy", "mary",
    "alice", "lisa", "anna", "emily", "jessica", "chloe", "sophie", "elena", "rachel",
    "woman", "girl", "female", "lady", "mother", "mrs", "miss", "ms", "sister", "daughter",
    "student_f"
}

MALE_INDICATORS = {
    "ed", "tutor", "dr", "doctor", "collins", "agent", "examiner", "john", "alex", "ryan",
    "liam", "william", "thomas", "guy", "peter", "david", "michael", "george", "james",
    "robert", "brian", "eric", "steffan", "man", "boy", "male", "gentleman", "father",
    "mr", "brother", "son", "officer", "interviewer", "professor"
}


@st.cache_data(show_spinner="Connecting to Microsoft Neural Voice Engine...")
def get_all_english_voices() -> List[Dict[str, str]]:
    """Fetch all English voices available from edge-tts."""
    async def _fetch():
        voices = await edge_tts.list_voices()
        en_voices = [
            {
                "ShortName": v.get("ShortName"),
                "FriendlyName": v.get("FriendlyName", v.get("ShortName")),
                "Locale": v.get("Locale", "en"),
                "Gender": v.get("Gender", "Unknown")
            }
            for v in voices
            if v.get("Locale", "").lower().startswith("en-")
        ]
        en_voices.sort(key=lambda x: (x["Locale"], x["Gender"], x["ShortName"]))
        return en_voices

    try:
        return asyncio.run(_fetch())
    except Exception:
        return [
            {"ShortName": k, "FriendlyName": v["name"], "Locale": v["locale"], "Gender": v["gender"]}
            for k, v in CURATED_IELTS_VOICES.items()
        ]


def clean_raw_input(raw_text: str) -> str:
    """Handles raw text, single/double escaped newlines, or JSON snippets."""
    raw_text = raw_text.strip()

    # Try full JSON parse if enclosed in braces
    if raw_text.startswith("{") and raw_text.endswith("}"):
        try:
            data = json.loads(raw_text)
            if isinstance(data, dict) and "transcript" in data:
                return str(data["transcript"])
        except Exception:
            pass

    # Check for "transcript": "..." or transcript: "..."
    prefix_match = re.search(r'^(?:\{?\s*["\']?transcript["\']?\s*:\s*)(.*)$', raw_text, re.DOTALL | re.IGNORECASE)
    if prefix_match:
        content = prefix_match.group(1).strip()
        content = re.sub(r'[\s,}]*$', '', content)
        if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
            content = content[1:-1]
        content = content.replace(r'\"', '"').replace(r"\'", "'").replace(r'\n', '\n').replace(r'\t', ' ')
        return content

    if r"\n" in raw_text:
        raw_text = raw_text.replace(r"\n", "\n")

    return raw_text


def parse_dialogue_or_monologue(raw_text: str) -> Tuple[List[Dict[str, any]], bool]:
    """
    Parses transcript and identifies:
    - Multi-speaker dialogues ([Speaker]: Text)
    - Exam pauses ([Pause: 30 seconds], [Pause: 15s], etc.)
    - Single speaker monologues

    Returns: (list_of_items, is_monologue)
    Each item is:
      {"type": "dialogue", "speaker": "Tutor", "text": "..."}
      OR
      {"type": "pause", "duration_ms": 30000, "label": "[Pause: 30 seconds]"}
    """
    cleaned = clean_raw_input(raw_text)
    lines = cleaned.splitlines()

    speaker_pattern = re.compile(r"^\s*(?:\[([^\]]+)\]|([A-Za-z0-9_\-\s]{1,30}))\s*:\s*(.+)$")
    pause_pattern = re.compile(r"^\s*\[Pause\s*:\s*(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|milliseconds?|ms)?\]\s*$", re.IGNORECASE)

    parsed_items: List[Dict[str, any]] = []
    has_tagged_speakers = False

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. Check for [Pause: X seconds]
        pause_match = pause_pattern.match(line_clean)
        if pause_match:
            val = float(pause_match.group(1))
            unit = (pause_match.group(2) or "seconds").lower()
            if unit.startswith("m"):
                ms = int(val)
            else:
                ms = int(val * 1000)
            parsed_items.append({
                "type": "pause",
                "duration_ms": ms,
                "label": line_clean
            })
            continue

        # 2. Check for [Speaker]: Dialogue
        match = speaker_pattern.match(line_clean)
        if match:
            speaker_tag = (match.group(1) or match.group(2)).strip()
            content = match.group(3).strip()
            if len(speaker_tag.split()) <= 4 and not any(c in speaker_tag for c in ".!?,;()"):
                has_tagged_speakers = True
                parsed_items.append({
                    "type": "dialogue",
                    "speaker": speaker_tag,
                    "text": content
                })
                continue

        # 3. Continuation of previous line or narration
        if parsed_items and parsed_items[-1]["type"] == "dialogue":
            parsed_items[-1]["text"] += f" {line_clean}"
        else:
            parsed_items.append({
                "type": "dialogue",
                "speaker": "Speaker",
                "text": line_clean
            })

    if not has_tagged_speakers:
        # Full monologue
        dialogue_texts = [item["text"] for item in parsed_items if item["type"] == "dialogue"]
        full_monologue_text = " ".join(dialogue_texts).strip()
        # Keep any pauses if present
        filtered_items = []
        for item in parsed_items:
            if item["type"] == "pause":
                filtered_items.append(item)
            elif not any(x.get("speaker") == "Speaker" for x in filtered_items):
                filtered_items.append({"type": "dialogue", "speaker": "Speaker", "text": full_monologue_text})
        return filtered_items, True

    dialogue_speakers = {item["speaker"].lower() for item in parsed_items if item["type"] == "dialogue"}
    is_monologue = (len(dialogue_speakers) == 1)

    return parsed_items, is_monologue


def normalize_ielts_speech_text(text: str) -> str:
    """
    Normalizes transcript text specifically for natural edge-tts conversational delivery:
    1. Expands hyphenated spelling (e.g. J-A-M-I-E-S-O-N -> J. A. M. I. E. S. O. N.)
    2. Replaces em-dashes and long hyphens with natural breath pauses
    3. Normalizes time references (9:30 AM -> 9:30 AM)
    4. Handles conversational openers naturally (Oh, hello -> Oh, hello.)
    """
    # 1. Hyphenated spelling like J-A-M-I-E-S-O-N -> "J. A. M. I. E. S. O. N."
    def expand_spelling(m):
        letters = m.group(0).split("-")
        return " ".join([f"{ltr.upper()}." for ltr in letters])

    text = re.sub(r"\b[A-Za-z](?:-[A-Za-z])+\b", expand_spelling, text)

    # 2. Time expressions
    text = re.sub(r"(\d+:\d+)\s*(AM|PM|am|pm)", r"\1 \2", text)

    # 3. Replace dashes with natural comma pauses to prevent robotic truncation
    text = text.replace("—", ", ").replace("–", ", ")

    # 4. Clean trailing spaces
    return text.strip()


def smart_match_edge_voice(speaker_name: str, used_voices: List[str], all_available: List[str]) -> str:
    """Smartly assigns natural edge-tts voice based on character name heuristics & role."""
    name_clean = speaker_name.lower().strip()
    words = set(re.findall(r"\b\w+\b", name_clean))

    is_female = any(w in FEMALE_INDICATORS for w in words)
    is_male = any(w in MALE_INDICATORS for w in words)

    # Ordered by conversational warmth and natural human inflection
    female_pool = [
        "en-GB-SoniaNeural",
        "en-AU-NatashaNeural",
        "en-GB-MaisieNeural",
        "en-GB-LibbyNeural",
        "en-US-JennyNeural",
        "en-CA-ClaraNeural",
        "en-IE-EmilyNeural",
        "en-US-AvaMultilingualNeural",
    ]

    male_pool = [
        "en-GB-RyanNeural",
        "en-GB-ThomasNeural",
        "en-AU-WilliamMultilingualNeural",
        "en-US-BrianMultilingualNeural",
        "en-US-GuyNeural",
        "en-CA-LiamNeural",
        "en-NZ-MitchellNeural",
    ]

    # Specific IELTS roles matching
    if "narrator" in words:
        # Official British exam narrator (Thomas or Sonia)
        candidate_pool = ["en-GB-ThomasNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural"]
    elif "tutor" in words or "doctor" in words or "collins" in words:
        # Academic Tutor (Ryan or Thomas)
        candidate_pool = ["en-GB-RyanNeural", "en-GB-ThomasNeural", "en-US-BrianMultilingualNeural"]
    elif "ruth" in words:
        # Student Ruth (Sonia, Natasha, or Maisie)
        candidate_pool = ["en-GB-SoniaNeural", "en-AU-NatashaNeural", "en-GB-MaisieNeural"]
    elif "ed" in words:
        # Student Ed (William or Liam or Guy)
        candidate_pool = ["en-AU-WilliamMultilingualNeural", "en-CA-LiamNeural", "en-US-GuyNeural", "en-GB-RyanNeural"]
    elif "amber" in words:
        candidate_pool = female_pool
    elif "agent" in words or "examiner" in words:
        candidate_pool = male_pool
    elif is_female and not is_male:
        candidate_pool = female_pool
    elif is_male and not is_female:
        candidate_pool = male_pool
    else:
        candidate_pool = female_pool if len(used_voices) % 2 == 1 else male_pool

    # Pick first available from pool that hasn't been used yet
    for v in candidate_pool:
        if v not in used_voices and (v in all_available or not all_available):
            return v

    for v in candidate_pool:
        if v in all_available or not all_available:
            return v

    return "en-GB-RyanNeural"


async def generate_single_turn_audio(
    text: str,
    voice: str,
    rate_str: str,
    pitch_str: str,
    output_path: str
):
    """Generate audio using edge-tts Communicate with rate and pitch settings."""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate_str,
        pitch=pitch_str
    )
    await communicate.save(output_path)


def synthesize_natural_dialogue(
    parsed_dialogue: List[Dict[str, any]],
    speaker_voice_map: Dict[str, str],
    base_rate_pct: int = -2,
    base_pitch_hz: int = 0,
    enable_rhythm_jitter: bool = True,
    turn_pause_range: Tuple[int, int] = (420, 620),
    sentence_pause_range: Tuple[int, int] = (200, 300),
    progress_bar=None,
    status_text=None
) -> io.BytesIO:
    """
    Synthesizes natural, human-like dialogue using Microsoft Neural Voices:
    - Pre-normalizes conversational text (spelled letters, times, dashes)
    - Adds subtle conversational rhythm variations (organic human pace jitter)
    - Automatically executes explicit exam pause gaps ([Pause: 30 seconds])
    - Inserts human turn-taking pauses with organic duration windows
    - Smoothly stitches audio using pydub
    """
    combined_audio = AudioSegment.empty()
    total_items = len(parsed_dialogue)

    with tempfile.TemporaryDirectory() as tmp_dir:
        last_speaker = None
        turn_counter = 0

        for idx, item in enumerate(parsed_dialogue):
            item_type = item.get("type", "dialogue")

            # 1. Handle explicit exam Pause blocks
            if item_type == "pause":
                pause_ms = item["duration_ms"]
                pause_sec = pause_ms / 1000.0
                if status_text:
                    status_text.text(f"Inserting Exam Silence: {item['label']} ({pause_sec:.1f}s)...")
                
                # Append explicit exam pause duration
                combined_audio += AudioSegment.silent(duration=pause_ms)
                last_speaker = None  # Reset speaker transition after long exam silence
                if progress_bar:
                    progress_bar.progress((idx + 1) / total_items)
                continue

            # 2. Handle dialogue turn
            speaker = item["speaker"]
            raw_text = item["text"]
            speech_text = normalize_ielts_speech_text(raw_text)
            voice_id = speaker_voice_map.get(speaker, "en-GB-RyanNeural")

            # Conversational rhythm jitter
            word_count = len(speech_text.split())
            if enable_rhythm_jitter:
                jitter = random.randint(-2, 2)
                # Official narrator speaks at calm measured pace
                if "narrator" in speaker.lower():
                    turn_rate = base_rate_pct - 1
                elif word_count <= 4:
                    turn_rate = base_rate_pct + 4 + jitter
                else:
                    turn_rate = base_rate_pct + jitter
            else:
                turn_rate = base_rate_pct

            rate_str = f"{turn_rate:+d}%"
            pitch_str = f"{base_pitch_hz:+d}Hz"

            if status_text:
                status_text.text(f"Speaking [{speaker}]: \"{raw_text[:40]}...\" ({idx + 1}/{total_items})")

            tmp_file = os.path.join(tmp_dir, f"turn_{turn_counter}.mp3")
            turn_counter += 1
            asyncio.run(generate_single_turn_audio(speech_text, voice_id, rate_str, pitch_str, tmp_file))

            clip = AudioSegment.from_file(tmp_file, format="mp3")

            # Dynamic human-like turn-taking pauses
            if len(combined_audio) > 0 and last_speaker is not None:
                if last_speaker != speaker:
                    # Random human turn-taking gap between speakers
                    p_duration = random.randint(turn_pause_range[0], turn_pause_range[1])
                    combined_audio += AudioSegment.silent(duration=p_duration)
                else:
                    # Consecutive lines by the same speaker
                    p_duration = random.randint(sentence_pause_range[0], sentence_pause_range[1])
                    combined_audio += AudioSegment.silent(duration=p_duration)

            combined_audio += clip
            last_speaker = speaker

            if progress_bar:
                progress_bar.progress((idx + 1) / total_items)

        output_buffer = io.BytesIO()
        combined_audio.export(output_buffer, format="mp3", bitrate="192k")
        output_buffer.seek(0)
        return output_buffer


def main():
    st.markdown('<div class="main-header">🎙️ IELTS Natural Conversational TTS Studio</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Human-like multi-speaker IELTS audio powered by Microsoft Azure Neural voices with exam pauses ([Pause: 30 seconds]), multi-character matching, and natural prosody.</div>',
        unsafe_allow_html=True
    )

    # 1. Fetch available voices
    all_voices = get_all_english_voices()
    all_shortnames = [v["ShortName"] for v in all_voices]

    # Build friendly selectbox options
    voice_options = {}
    for v in all_voices:
        sname = v["ShortName"]
        if sname in CURATED_IELTS_VOICES:
            meta = CURATED_IELTS_VOICES[sname]
            label = f"⭐ {meta['name']} ({sname})"
        else:
            label = f"{sname} ({v.get('Locale', 'en')} - {v.get('Gender', 'Voice')})"
        voice_options[label] = sname

    voice_labels = list(voice_options.keys())

    # Sidebar: Conversational Naturalness Controls
    with st.sidebar:
        st.header("✨ Human Conversational Tuning")
        st.caption("Acoustic adjustments that turn synthetic audio into natural conversations.")

        enable_rhythm_jitter = st.toggle(
            "Conversational Rhythm Jitter",
            value=True,
            help="Subtly varies speaking rate (+/- 2%) between turns and paces quick replies faster, mimicking real human conversation."
        )

        base_rate = st.slider(
            "Speaking Pace (Rate):",
            min_value=-15,
            max_value=10,
            value=-3,
            step=1,
            format="%d%%",
            help="-3% to -5% is the gold standard for clear, articulate British/Australian IELTS dialogues."
        )

        base_pitch = st.slider(
            "Voice Pitch:",
            min_value=-5,
            max_value=5,
            value=0,
            step=1,
            format="%dHz"
        )

        st.subheader("⏱️ Natural Turn-Taking Pauses")
        turn_gap_min, turn_gap_max = st.slider(
            "Turn Pause Range (ms):",
            min_value=250,
            max_value=900,
            value=(420, 600),
            step=25,
            help="Realistic randomized silence window between different speakers."
        )

        st.markdown("---")
        st.markdown("**Transcript Features Supported:**")
        st.markdown("✅ `[Pause: 30 seconds]` (Exact exam pauses)")
        st.markdown("✅ `[Narrator]: ...` (Exam instructions)")
        st.markdown("✅ Multi-characters (`[Tutor]`, `[Ruth]`, `[Ed]`)")
        st.markdown("✅ Spelled letters (`J-A-M-I-E-S-O-N`)")

    # 2. Input Script Section
    st.markdown("### 1. Script / Dialogue Input")

    col_btn1, col_btn2, _ = st.columns([1.8, 1.8, 2.4])
    with col_btn1:
        if st.button("Load IELTS Part 3 (Narrator, Tutor, Ruth & Ed)"):
            st.session_state["transcript_input"] = (
                "[Narrator]: Part 3. You will hear two psychology students, Ruth and Ed, discussing their research on birth order and personality with their tutor.\n"
                "[Narrator]: First, you have some time to look at questions 21 to 26.\n"
                "[Pause: 30 seconds]\n\n"
                "[Tutor]: Come in, Ruth and Ed. Let's talk through your psychology seminar presentation on birth order and personality development.\n"
                "[Ed]: Thanks, Dr Collins. We've reviewed extensive literature, including Francis Galton's early work and modern psychological studies.\n"
                "[Ruth]: Right. It's fascinating how strongly popular culture associates birth order with distinct personality traits. For example, first-born children are commonly expected to be natural leaders and highly conscientious.\n"
                "[Tutor]: Yes, and what did you find regarding eldest siblings?\n"
                "[Ed]: Well, empirical findings show eldest siblings often display high academic achievement, but popular stereotypes that they are rigid or introverted aren't consistently supported.\n"
                "[Ruth]: And with middle children, public perception often describes them as peacemakers and exceptional negotiators, because they grew up mediating between older and younger siblings.\n"
                "[Ed]: On the other hand, the youngest child in a family is frequently characterised as rebellious and willing to take risks, seeking distinction from older brothers and sisters.\n"
                "[Ruth]: As for only children, they often suffer from the stereotype of being selfish or spoiled, but research indicates they are actually very self-confident and articulate because of extensive adult interaction.\n"
                "[Ed]: And identical twins raised together showed strong mutual empathy and cooperative tendencies, though sometimes struggling to establish individual identity.\n\n"
                "[Narrator]: Before you hear the rest of the discussion, you have some time to look at questions 27 to 30.\n"
                "[Pause: 30 seconds]\n\n"
                "[Tutor]: What about the methodology in earlier birth order studies? What flaws did you identify?\n"
                "[Ruth]: A major methodological weakness was sample bias. Many early studies failed to control for family socioeconomic status and family size. A large family has very different dynamics than a two-child family.\n"
                "[Ed]: Exactly. When modern researchers controlled for socioeconomic background, many supposed birth order effects vanished.\n"
                "[Tutor]: And what are the two main conclusions for your presentation slides?\n"
                "[Ruth]: First, we want to emphasize that parental expectations shape behaviour far more decisively than birth rank alone.\n"
                "[Ed]: And second, that sibling spacing—the number of years between children—plays a far greater role than simple sequence.\n\n"
                "[Narrator]: That is the end of Part 3. You now have half a minute to check your answers.\n"
                "[Pause: 30 seconds]"
            )
    with col_btn2:
        if st.button("Load IELTS Part 1 (Agent & Amber)"):
            st.session_state["transcript_input"] = (
                "[Agent]: Good morning, Bankside Recruitment Agency. Can I help you?\n"
                "[Amber]: Oh, hello. I'm calling to register with your agency for temporary work.\n"
                "[Agent]: Certainly. May I take your name first?\n"
                "[Amber]: Yes, it's Amber Jamieson.\n"
                "[Agent]: Could you spell the surname for me, please?\n"
                "[Amber]: That's J-A-M-I-E-S-O-N."
            )

    default_text = st.session_state.get(
        "transcript_input",
        "[Narrator]: Part 3. You will hear two psychology students, Ruth and Ed, discussing their research on birth order and personality with their tutor.\n"
        "[Narrator]: First, you have some time to look at questions 21 to 26.\n"
        "[Pause: 30 seconds]\n\n"
        "[Tutor]: Come in, Ruth and Ed. Let's talk through your psychology seminar presentation on birth order and personality development.\n"
        "[Ed]: Thanks, Dr Collins. We've reviewed extensive literature, including Francis Galton's early work and modern psychological studies.\n"
        "[Ruth]: Right. It's fascinating how strongly popular culture associates birth order with distinct personality traits."
    )

    transcript_text = st.text_area(
        label="Paste transcript, JSON string, or monologue:",
        value=default_text,
        height=240,
        placeholder="Paste your conversation or monologue text here..."
    )

    if not transcript_text.strip():
        st.info("👆 Paste or enter your text above to proceed.")
        return

    # 3. Parse Transcript & Detect Mode
    parsed_items, is_monologue = parse_dialogue_or_monologue(transcript_text)
    
    # Extract unique speakers (excluding pause items)
    dialogue_items = [item for item in parsed_items if item.get("type") == "dialogue"]
    pause_items = [item for item in parsed_items if item.get("type") == "pause"]
    unique_speakers = sorted(list({item["speaker"] for item in dialogue_items}))

    # Display status badge
    if is_monologue:
        st.markdown(
            '<span class="monologue-badge">🎙️ Single-Speaker Monologue Detected</span> '
            f'<span style="color:#64748B; font-size:0.9rem;">({len(dialogue_items)} dialogue units, {len(pause_items)} pauses)</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<span class="speaker-badge">👥 Multi-Character Dialogue Detected ({len(unique_speakers)} Speakers)</span> '
            f'<span style="color:#64748B; font-size:0.9rem;">({len(dialogue_items)} spoken turns, {len(pause_items)} exam pauses)</span>',
            unsafe_allow_html=True
        )

    # 4. Smart Character Voice Mapping
    st.markdown("### 2. Character Voice Mapping")

    speaker_voice_map: Dict[str, str] = {}
    used_voices: List[str] = []

    smart_defaults: Dict[str, str] = {}
    for speaker in unique_speakers:
        matched = smart_match_edge_voice(speaker, used_voices, all_shortnames)
        smart_defaults[speaker] = matched
        used_voices.append(matched)

    cols = st.columns(max(1, min(len(unique_speakers), 4)))
    for idx, speaker in enumerate(unique_speakers):
        col = cols[idx % len(cols)]
        recommended_key = smart_defaults[speaker]

        def_index = 0
        for i, (lbl, sname) in enumerate(voice_options.items()):
            if sname == recommended_key:
                def_index = i
                break

        with col:
            prompt_label = f"Voice for **{speaker}** (Auto-assigned):" if not is_monologue else "Narrator / Speaker Voice:"
            selected_label = st.selectbox(
                prompt_label,
                options=voice_labels,
                index=def_index,
                key=f"voice_select_{speaker}"
            )
            speaker_voice_map[speaker] = voice_options[selected_label]

    # Interactive Breakdown View
    with st.expander("🔍 View Script, Pauses & Speech Preview", expanded=False):
        for idx, item in enumerate(parsed_items, 1):
            if item.get("type") == "pause":
                st.markdown(
                    f"<div class='pause-box'><b>#{idx}</b> <span class='pause-badge'>⏸️ Exam Pause</span> "
                    f"Silence gap: <b>{item['duration_ms'] / 1000.0} seconds</b> ({item['label']})</div>",
                    unsafe_allow_html=True
                )
            else:
                normalized_line = normalize_ielts_speech_text(item['text'])
                assigned_v = speaker_voice_map.get(item['speaker'], '')
                is_narrator = "narrator" in item['speaker'].lower()
                badge_class = "narrator-badge" if is_narrator else "speaker-badge"
                st.markdown(
                    f"<div class='line-box'><b>#{idx}</b> <span class='{badge_class}'>{item['speaker']}</span> "
                    f"<small style='color:#6B7280;'>({assigned_v})</small><br/>"
                    f"<b>Text:</b> {item['text']}<br/>"
                    f"<b>Acoustic Input:</b> <i>{normalized_line}</i></div>",
                    unsafe_allow_html=True
                )

    # 5. Audio Synthesis
    st.markdown("### 3. Generate Audio")
    if st.button("🚀 Synthesize Full IELTS Exam Audio", type="primary", use_container_width=True):
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        try:
            with st.spinner("Synthesizing multi-character dialogue & assembling exam pauses with Microsoft Neural Engine..."):
                audio_buffer = synthesize_natural_dialogue(
                    parsed_dialogue=parsed_items,
                    speaker_voice_map=speaker_voice_map,
                    base_rate_pct=base_rate,
                    base_pitch_hz=base_pitch,
                    enable_rhythm_jitter=enable_rhythm_jitter,
                    turn_pause_range=(turn_gap_min, turn_gap_max),
                    progress_bar=progress_bar,
                    status_text=status_text
                )

            progress_bar.progress(1.0)
            status_text.success("Audio synthesized successfully with full multi-speaker dialogue and exam pauses!")
            st.session_state["edge_generated_audio"] = audio_buffer.getvalue()
        except Exception as e:
            status_text.error(f"Error during audio generation: {e}")

    # 6. Playback & Export
    if "edge_generated_audio" in st.session_state:
        st.markdown("### 4. Audio Playback & Export")
        st.audio(st.session_state["edge_generated_audio"], format="audio/mp3")

        st.download_button(
            label="📥 Download Complete IELTS Audio (MP3)",
            data=st.session_state["edge_generated_audio"],
            file_name="ielts_part3_practice.mp3",
            mime="audio/mp3",
            type="primary"
        )


if __name__ == "__main__":
    main()
