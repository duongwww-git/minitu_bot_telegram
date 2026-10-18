"""Voice helpers: download a Telegram voice note and transcribe it (Slot B)."""

from lib import ai, tg


class VoiceError(Exception):
    pass


def download(file_id):
    if not file_id:
        raise VoiceError("missing file_id")
    try:
        path = tg.get_file_path(file_id)
    except Exception as e:
        raise VoiceError(f"getFile failed: {e}") from e
    if not path:
        raise VoiceError("no file_path returned by Telegram")
    try:
        return tg.download_file(path)
    except Exception as e:
        raise VoiceError(f"download failed: {e}") from e


def transcribe(file_id):
    """Download + transcribe. Raises ai.AIRateLimited / ai.AIError."""
    audio = download(file_id)
    return ai.transcribe(audio, mime_type="audio/ogg")
