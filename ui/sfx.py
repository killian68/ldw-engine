import os

# Lazy-loaded mixer state
_mixer_initialized = False


def _init_mixer():
    global _mixer_initialized
    if _mixer_initialized:
        return

    try:
        import pygame
        pygame.mixer.init()
        _mixer_initialized = True
    except Exception:
        # Fail silently (no sound)
        _mixer_initialized = False


def play_wav(wav_path: str):
    """
    Cross-platform async WAV playback using pygame.mixer.
    Fails silently if pygame is not available or sound cannot be played.
    """
    if not os.path.exists(wav_path):
        return

    try:
        import pygame

        _init_mixer()

        if not _mixer_initialized:
            return

        sound = pygame.mixer.Sound(wav_path)
        sound.play()  # async by default

    except Exception:
        # Never crash the UI because of sound
        pass