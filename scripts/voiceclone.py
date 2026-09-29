#!/usr/bin/env python3
"""Backward-compatible MiMo voice cloning command."""
import sys
from mimo_audio import (BASE_URL, MODELS, audio_data_uri, build_speech_request,
                        entrypoint, load_api_key, wav_info)

MODEL = MODELS["voiceclone"]


def build_request(text, reference, instruction=""):
    """Keep the original PCM WAV request helper available."""
    wav_info(reference)
    return build_speech_request("voiceclone", text, instruction,
                                reference_uri=audio_data_uri(reference, "audio/wav"))


def main():
    return entrypoint(["voiceclone", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
