# IELTS Multi-Speaker Natural Dialogue TTS Studio

A fast, free, and natural conversational Text-to-Speech (TTS) web application tailored for IELTS dialogue and monologue practice, powered by Microsoft Azure Neural voices via `edge-tts` and stitched seamlessly with `pydub`.

## Key Features & Natural Conversational Enhancements
- **Natural Human Turn-Taking (Not Robotic)**: Replaces fixed pauses with organic, randomized turn-taking gaps (420 ms – 620 ms) between speakers.
- **Conversational Rhythm Jitter**: Subtly varies speech rate per line: quick affirmations ("Of course", "Right, I will") are spoken faster, while explanations are delivered at a measured, articulate IELTS tempo.
- **Acoustic Speech Normalizer**: Automatically recites spelled-out names (e.g. `J-A-M-I-E-S-O-N` $\rightarrow$ `J. A. M. I. E. S. O. N.`) and softens punctuation/em-dashes to eliminate synthetic glitches.
- **Smart Character & Voice Detection**:
  - Automatically identifies whether an input is a multi-speaker dialogue or a single-speaker monologue (e.g., Section 4 lecture).
  - Intelligently pairs character names with gender-accurate British, Australian, or international neural voices (`Ryan`, `Sonia`, `Maisie`, `Natasha`, etc.).
  - Accepts raw dialogs (`[Agent]: ...`), plain monologues, or JSON formatted snippets (`"transcript": "..."`).
- **Zero API Keys & CPU Friendly**: Runs locally without any keys or GPU requirements.

---

## Quick Start

1. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

2. **Launch the web application**:
   ```bash
   ./venv/bin/streamlit run app.py
   ```

3. Open your browser at `http://localhost:8501`.
