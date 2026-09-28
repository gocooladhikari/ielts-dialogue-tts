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
        .line-box {
            background: #F8FAFC;
            border-left: 3px solid #3B82F6;
            padding: 10px 14px;
            margin-bottom: 8px;
            border-radius: 0 6px 6px 0;
            font-size: 0.94rem;
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
# These are hand-selected for natural inflection, expressive human breath, and authenticity
CURATED_IELTS_VOICES = {
    # British English (Primary IELTS Accent)
    "en-GB-RyanNeural": {"name": "Ryan (British Male - Friendly & Expressive)", "gender": "Male", "locale": "en-GB"},
    "en-GB-SoniaNeural": {"name": "Sonia (British Female - Crisp & Professional)", "gender": "Female", "locale": "en-GB"},
    "en-GB-ThomasNeural": {"name": "Thomas (British Male - Calm & Articulate)", "gender": "Male", "locale": "en-GB"},
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
    "amber", "sarah", "emma", "jenny", "sonia", "clara", "natasha", "lucy", "mary",
    "alice", "lisa", "anna", "emily", "jessica", "chloe", "sophie", "elena", "rachel",
    "woman", "girl", "female", "lady", "mother", "mrs", "miss", "ms", "sister", "daughter"
}

MALE_INDICATORS = {
    "agent", "examiner", "john", "alex", "ryan", "liam", "william", "thomas", "guy",
    "peter", "david", "michael", "george", "james", "robert", "brian", "eric", "steffan",
    "man", "boy", "male", "gentleman", "father", "mr", "brother", "son", "officer", "interviewer"
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
        # Fallback to curated dictionary if network blip
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


def parse_dialogue_or_monologue(raw_text: str) -> Tuple[List[Dict[str, str]], bool]:
    """
    Parses transcript and identifies whether it's a multi-speaker dialogue or single speaker monologue.
    Returns: (list_of_lines, is_monologue)
    """
    cleaned = clean_raw_input(raw_text)
    lines = cleaned.splitlines()

    speaker_pattern = re.compile(r"^\s*(?:\[([^\]]+)\]|([A-Za-z0-9_\-\s]{1,30}))\s*:\s*(.+)$")
    parsed_lines: List[Dict[str, str]] = []
    has_tagged_speakers = False

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        match = speaker_pattern.match(line_clean)
        if match:
            speaker_tag = (match.group(1) or match.group(2)).strip()
            content = match.group(3).strip()
            if len(speaker_tag.split()) <= 4 and not any(c in speaker_tag for c in ".!?,;()"):
                has_tagged_speakers = True
                parsed_lines.append({"speaker": speaker_tag, "text": content})
                continue

        if parsed_lines:
            parsed_lines[-1]["text"] += f" {line_clean}"
        else:
            parsed_lines.append({"speaker": "Speaker", "text": line_clean})

    if not has_tagged_speakers:
        full_monologue_text = " ".join([item["text"] for item in parsed_lines]).strip()
        return [{"speaker": "Speaker", "text": full_monologue_text}], True

    unique_speakers = {item["speaker"].lower() for item in parsed_lines}
    is_monologue = (len(unique_speakers) == 1)

    return parsed_lines, is_monologue


def normalize_ielts_speech_text(text: str) -> str:
    """
    Normalizes transcript text specifically for natural edge-tts conversational delivery:
    1. Expands hyphenated spelling (e.g. J-A-M-I-E-S-O-N -> J... A... M... I... E... S... O... N.)
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
        "en-AU-WilliamMultilingualNeural",
        "en-GB-ThomasNeural",
        "en-US-BrianMultilingualNeural",
        "en-US-GuyNeural",
        "en-CA-LiamNeural",
        "en-NZ-MitchellNeural",
    ]

    if "amber" in words:
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
    parsed_dialogue: List[Dict[str, str]],
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
    - Inserts human turn-taking pauses with organic duration windows
    - Smoothly stitches audio using pydub
    """
    combined_audio = AudioSegment.empty()
    total_lines = len(parsed_dialogue)

    with tempfile.TemporaryDirectory() as tmp_dir:
        last_speaker = None
        for idx, item in enumerate(parsed_dialogue):
            speaker = item["speaker"]
            raw_text = item["text"]

            # 1. Normalize text for speech prosody
            speech_text = normalize_ielts_speech_text(raw_text)
            voice_id = speaker_voice_map.get(speaker, "en-GB-RyanNeural")

            # 2. Conversational rhythm jitter
            # Humans speak short affirmations ("Of course", "Right, I will") slightly quicker,
            # and longer explanations at a measured tempo.
            word_count = len(speech_text.split())
            if enable_rhythm_jitter:
                jitter = random.randint(-2, 2)
                if word_count <= 4:
                    turn_rate = base_rate_pct + 4 + jitter
                else:
                    turn_rate = base_rate_pct + jitter
            else:
                turn_rate = base_rate_pct

            rate_str = f"{turn_rate:+d}%"
            pitch_str = f"{base_pitch_hz:+d}Hz"

            if status_text:
                status_text.text(f"Speaking [{speaker}]: \"{raw_text[:40]}...\" ({idx + 1}/{total_lines})")

            tmp_file = os.path.join(tmp_dir, f"turn_{idx}.mp3")
            asyncio.run(generate_single_turn_audio(speech_text, voice_id, rate_str, pitch_str, tmp_file))

            clip = AudioSegment.from_file(tmp_file, format="mp3")

            # 3. Dynamic human-like turn-taking pauses
            if len(combined_audio) > 0:
                if last_speaker and last_speaker != speaker:
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
                progress_bar.progress((idx + 1) / total_lines)

        output_buffer = io.BytesIO()
        combined_audio.export(output_buffer, format="mp3", bitrate="192k")
        output_buffer.seek(0)
        return output_buffer


def main():
    st.markdown('<div class="main-header">🎙️ IELTS Natural Conversational TTS Studio</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Human-like multi-speaker IELTS audio powered by Microsoft Azure Neural voices with organic turn-taking pauses, prosodic rhythm, and acoustic letter spelling.</div>',
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
        st.markdown("**Conversational Speech Normalizer:**")
        st.markdown("✅ Spelled letters (`J-A-M-I-E-S-O-N` $\\rightarrow$ natural acoustic recitation)")
        st.markdown("✅ Conversational pauses on em-dashes and commas")
        st.markdown("✅ Time phrases and numbers articulated naturally")

    # 2. Input Script Section
    st.markdown("### 1. Script / Dialogue Input")

    col_btn1, col_btn2, _ = st.columns([1.6, 1.6, 2.8])
    with col_btn1:
        if st.button("Load Multi-Speaker Dialogue (Agent & Amber)"):
            st.session_state["transcript_input"] = (
                "[Agent]: Good morning, Bankside Recruitment Agency. Can I help you?\n"
                "[Amber]: Oh, hello. I'm calling to register with your agency for temporary work.\n"
                "[Agent]: Certainly. May I take your name first?\n"
                "[Amber]: Yes, it's Amber Jamieson.\n"
                "[Agent]: Could you spell the surname for me, please?\n"
                "[Amber]: That's J-A-M-I-E-S-O-N.\n"
                "[Agent]: Thank you. And what kind of work are you primarily interested in, Amber?\n"
                "[Amber]: Well, clerical or administrative roles, ideally. I'm available mornings and early afternoons, but an afternoon shift would suit me best.\n"
                "[Agent]: Great, an afternoon placement is often easier to arrange. What would you say are your strongest professional skills?\n"
                "[Amber]: I have extensive administrative experience, and my communication skills are very strong—both written and on the phone.\n"
                "[Agent]: Excellent. We have a position opening next week for a receptionist at a legal firm. The assignment is scheduled to last for a week, with the possibility of extension.\n"
                "[Agent]: The pay rate starts at 10 pounds an hour.\n"
                "[Amber]: Ten pounds an hour sounds reasonable.\n"
                "[Agent]: Now, before we can send you on assignments, you'll need to attend an interview at our office. Please make sure you wear a suit for the interview.\n"
                "[Amber]: Of course.\n"
                "[Agent]: And remember to bring your passport as proof of your right to work in the UK.\n"
                "[Amber]: Right, I'll bring that along.\n"
                "[Agent]: You'll also take a short test online before coming in—it's a personality assessment to help match you to company cultures.\n"
                "[Amber]: Okay, no problem.\n"
                "[Agent]: Afterwards, we always ask clients to provide feedback on our candidates so we can support your ongoing development.\n"
                "[Amber]: That's very helpful. What time should I arrive on Tuesday?\n"
                "[Agent]: Please be here right on time, at 9:30 AM.\n"
                "[Amber]: Thank you very much!"
            )
    with col_btn2:
        if st.button("Load Single-Speaker IELTS Talk (Section 4)"):
            st.session_state["transcript_input"] = (
                "Good morning everyone, and welcome to this lecture on sustainable urban architecture. "
                "Today, I'd like to look at how modern city planners are incorporating green rooftop gardens "
                "to reduce the urban heat island effect. In the first part of this talk, we'll examine the thermal properties "
                "of sedum plants, and then move on to water drainage management in high-density buildings."
            )

    default_text = st.session_state.get(
        "transcript_input",
        "[Agent]: Good morning, Bankside Recruitment Agency. Can I help you?\n"
        "[Amber]: Oh, hello. I'm calling to register with your agency for temporary work.\n"
        "[Agent]: Certainly. May I take your name first?\n"
        "[Amber]: Yes, it's Amber Jamieson."
    )

    transcript_text = st.text_area(
        label="Paste transcript, JSON string, or monologue:",
        value=default_text,
        height=220,
        placeholder="Paste your conversation or monologue text here..."
    )

    if not transcript_text.strip():
        st.info("👆 Paste or enter your text above to proceed.")
        return

    # 3. Parse Transcript & Detect Mode
    parsed_lines, is_monologue = parse_dialogue_or_monologue(transcript_text)
    unique_speakers = sorted(list({item["speaker"] for item in parsed_lines}))

    if is_monologue:
        st.markdown(
            '<span class="monologue-badge">🎙️ Single-Speaker Monologue Detected</span> '
            '<span style="color:#64748B; font-size:0.9rem;">(Lecture / Part 2 / Part 4 style)</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<span class="speaker-badge">👥 Multi-Character Dialogue Detected ({len(unique_speakers)} Speakers)</span> '
            f'<span style="color:#64748B; font-size:0.9rem;">({len(parsed_lines)} conversational turns)</span>',
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

    cols = st.columns(max(1, min(len(unique_speakers), 3)))
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

    with st.expander("🔍 View Script & Speech Normalization Preview", expanded=False):
        for idx, item in enumerate(parsed_lines, 1):
            normalized_line = normalize_ielts_speech_text(item['text'])
            if is_monologue:
                st.markdown(f"<div class='line-box'>{item['text']}</div>", unsafe_allow_html=True)
            else:
                assigned_v = speaker_voice_map.get(item['speaker'], '')
                st.markdown(
                    f"<div class='line-box'><b>#{idx}</b> <span class='speaker-badge'>{item['speaker']}</span> "
                    f"<small style='color:#6B7280;'>({assigned_v})</small><br/>"
                    f"<b>Raw:</b> {item['text']}<br/>"
                    f"<b>Acoustic Speech Input:</b> <i>{normalized_line}</i></div>",
                    unsafe_allow_html=True
                )

    # 5. Audio Synthesis
    st.markdown("### 3. Generate Audio")
    if st.button("🚀 Synthesize Natural Dialogue", type="primary", use_container_width=True):
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        try:
            with st.spinner("Synthesizing dialogue lines with Microsoft Neural Engine & natural conversational timing..."):
                audio_buffer = synthesize_natural_dialogue(
                    parsed_dialogue=parsed_lines,
                    speaker_voice_map=speaker_voice_map,
                    base_rate_pct=base_rate,
                    base_pitch_hz=base_pitch,
                    enable_rhythm_jitter=enable_rhythm_jitter,
                    turn_pause_range=(turn_gap_min, turn_gap_max),
                    progress_bar=progress_bar,
                    status_text=status_text
                )

            progress_bar.progress(1.0)
            status_text.success("Audio synthesized successfully with natural conversational flow!")
            st.session_state["edge_generated_audio"] = audio_buffer.getvalue()
        except Exception as e:
            status_text.error(f"Error during audio generation: {e}")

    # 6. Playback & Export
    if "edge_generated_audio" in st.session_state:
        st.markdown("### 4. Audio Playback & Export")
        st.audio(st.session_state["edge_generated_audio"], format="audio/mp3")

        st.download_button(
            label="📥 Download IELTS Dialogue (MP3)",
            data=st.session_state["edge_generated_audio"],
            file_name="ielts_natural_dialogue.mp3",
            mime="audio/mp3",
            type="primary"
        )


if __name__ == "__main__":
    main()
