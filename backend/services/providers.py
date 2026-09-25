"""Provider interface — v1 has CaptionProvider only.

v2 adds WhisperProvider (yt-dlp + faster-whisper or OpenAI API)
without changing the API contract or frontend.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .youtube import fetch_caption_transcript, get_title


@dataclass
class TranscriptResult:
    video_id: str
    language: str
    segments: list = field(default_factory=list)
    title: str | None = None

    @property
    def plain_text(self) -> str:
        return " ".join(s["text"] for s in self.segments)


class TranscriptProvider(ABC):
    @abstractmethod
    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        raise NotImplementedError


class CaptionProvider(TranscriptProvider):
    """v1: YouTube captions only (manual > auto-generated)."""

    def get_transcript(self, video_id: str, lang: str = "en") -> TranscriptResult:
        segments, resolved_lang = fetch_caption_transcript(video_id, lang=lang)
        title = get_title(video_id)
        return TranscriptResult(
            video_id=video_id,
            language=resolved_lang,
            segments=segments,
            title=title,
        )


# v2 placeholder (do not implement in v1):
# class WhisperProvider(TranscriptProvider): ...
