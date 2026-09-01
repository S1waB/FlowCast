#!/usr/bin/env python3
"""
FlowCast E2E test script.
Generates a mock voice track with specific silences (short & long) to test
transition capping and centering logic.

Short silence: 0.8s (should be filled with a truncated transition without overlap).
Long silence: 6.0s (should hold a centered 5.0s transition + 1.0s of pure bed).
"""

import sys
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine

# Add backend directory to sys.path to import our app modules
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.audio_engine import assemble_bulletin

def generate_mock_voice_track(output_path: Path):
    """
    Creates a voice track with:
    - 3s "speech" (440Hz beep)
    - 0.8s silence
    - 3s "speech" (440Hz beep)
    - 6.0s silence
    - 3s "speech" (440Hz beep)
    """
    speech = Sine(440).to_audio_segment(duration=3000).apply_gain(-10)
    
    # 0.8s silence
    short_silence = AudioSegment.silent(duration=800)
    # 6.0s silence
    long_silence = AudioSegment.silent(duration=6000)
    
    track = speech + short_silence + speech + long_silence + speech
    track.export(str(output_path), format="wav")
    return output_path

def main():
    print("🎙️ Generating mock voice track with varied silences...")
    uploads_dir = backend_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    voice_path = uploads_dir / "e2e_mock_voice.wav"
    generate_mock_voice_track(voice_path)
    
    print("🚀 Running complete bulletin assembly pipeline...")
    output_dir = backend_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_output = output_dir / "e2e_test_result.mp3"
    
    try:
        result = assemble_bulletin(
            voice_clip_paths=[str(voice_path)],
            config_path=backend_dir / "config" / "source_bank.json",
            output_path=str(final_output)
        )
        print("✅ Assembly complete!")
        print(f"   Output saved to: {result.output_path}")
        print(f"   Transitions inserted: {result.transitions_count}")
        print(f"   Total duration: {result.duration_ms / 1000:.2f}s")
        print("\n🎧 Please listen to backend/output/e2e_test_result.mp3 manually to verify:")
        print("   - The first transition (at 3s) should be short and not overlap the speech.")
        print("   - The second transition (at 6.8s) should be full (5s) and centered within the 6s gap.")
    except Exception as e:
        print(f"❌ Error during assembly: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
