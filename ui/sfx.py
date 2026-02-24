import os

def play_wav(wav_path: str):
    try:
        import winsound
        if os.path.exists(wav_path):
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass