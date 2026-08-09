"""Speaking the beginning of a reply before the end of it exists.

The device answered nothing until the whole reply had been generated, then
synthesised all of it, then played it. On four Cortex-A76 cores that is around
three and a half seconds of silence for a fifty-token answer, and none of it is
work the listener needs to wait for: the first sentence is speakable while the
rest is still being decoded.

Two small pieces make that possible. The reply is one field inside a
schema-constrained JSON object, so it has to be lifted out of a document that is
still arriving — that is `ReplyFieldStream`. And speech wants a natural boundary
rather than a token boundary, so text is grouped into sentences before it reaches
the synthesiser — that is `SentenceChunker`.

Both are pure text handling with no I/O, because the interesting failures are all
in the parsing: escapes split across chunks, a terminator that turns out to be a
decimal point, a field name that is a prefix of another.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

# Called with each speakable piece as it becomes available. Awaited in sequence, so a
# listener that synthesises and plays keeps the sentences in order.
ReplyChunkListener = Callable[[str], Awaitable[None]]

# A full stop and a semicolon are ambiguous: "3.5" and "e.g." are not sentence ends,
# so these are only boundaries when whitespace follows and enough text has built up.
_AMBIGUOUS_TERMINATORS = ".;"
# These only ever end a sentence, so they need neither test. Both matter for this
# device: CJK writes no space after 。, so demanding one would never segment Chinese
# at all, and the danda is how Bengali and Hindi end sentences — the Pi profile's
# default recognition language is bn-BD, making that the common case, not an edge.
# The character minimum is also nearly meaningless for CJK, where a whole sentence
# can be three characters, so only a token floor applies.
_CLEAR_TERMINATORS = "!?…。！？；।॥۔\n"
_TERMINATORS = _AMBIGUOUS_TERMINATORS + _CLEAR_TERMINATORS
_MINIMUM_CLEAR_CHARACTERS = 2
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


# SentencePiece writes a word boundary as U+2581, and Gemma sometimes emits it literally
# instead of a space — observed as "help you plan.<mark><mark>Just let me know" from a real
# model. It has to be removed rather than tolerated for two reasons: eSpeak would try to
# pronounce it, and a full stop followed by U+2581 is not followed by whitespace, so
# SentenceChunker would not treat it as a sentence end and a whole reply would arrive as
# one late piece.
_WORD_BOUNDARY = "▁"


def normalise_model_text(text: str, *, collapse: bool = True) -> str:
    """Turn a model's word-boundary markers back into spaces.

    `collapse` is off while streaming: pieces arrive mid-sentence, and collapsing runs of
    spaces at a piece boundary would silently delete a legitimate one. Substitution alone
    is safe there because it is per-character.
    """
    if _WORD_BOUNDARY not in text:
        return text
    text = text.replace(_WORD_BOUNDARY, " ")
    if not collapse:
        return text
    return re.sub(r"[ 	]{2,}", " ", text).strip()


class ReplyFieldStream:
    """Extract one JSON string field's value from text arriving in pieces.

    A streaming decoder rather than a JSON parser: the document is incomplete for
    as long as it matters, so nothing can be parsed until the moment the value is
    no longer useful.

    The field name is matched including its closing quote, which is what keeps
    "reply" from matching "reply_template". The grammar the server is given emits
    the schema's fields in order, so the first occurrence is the real key rather
    than text that happens to look like one.
    """

    def __init__(self, field: str = "reply") -> None:
        self._needle = f'"{field}"'
        self._pending = ""
        self._inside = False
        self._done = False
        self._escape = False
        self._unicode: str | None = None
        self._high_surrogate: int | None = None

    @property
    def complete(self) -> bool:
        return self._done

    def feed(self, text: str) -> str:
        """Return whatever newly arrived text belongs to the field's value."""
        if self._done or not text:
            return ""
        if not self._inside:
            remainder = self._seek_opening_quote(text)
            if remainder is None:
                return ""
            text = remainder
        return self._consume(text)

    def _seek_opening_quote(self, text: str) -> str | None:
        """Advance to the first character of the value, or None if not there yet."""
        self._pending += text
        index = self._pending.find(self._needle)
        if index < 0:
            # Keep just enough to still match a needle split across two chunks.
            self._pending = self._pending[-len(self._needle) :]
            return None
        after_key = self._pending[index + len(self._needle) :].lstrip()
        if not after_key.startswith(":"):
            return None
        after_colon = after_key[1:].lstrip()
        if not after_colon.startswith('"'):
            return None
        self._pending = ""
        self._inside = True
        return after_colon[1:]

    def _consume(self, text: str) -> str:
        out: list[str] = []
        for character in text:
            if self._unicode is not None:
                self._unicode += character
                if len(self._unicode) == 4:
                    decoded = self._decode_escape(self._unicode)
                    if decoded:
                        out.append(decoded)
                    self._unicode = None
                continue
            if self._escape:
                self._escape = False
                if character == "u":
                    self._unicode = ""
                else:
                    out.append(_ESCAPES.get(character, character))
                continue
            if character == "\\":
                self._escape = True
                continue
            if character == '"':
                self._done = True
                break
            out.append(character)
        return "".join(out)

    def _decode_escape(self, digits: str) -> str:
        """Turn one \\uXXXX escape into text, pairing surrogates.

        Anything outside the Basic Multilingual Plane — an emoji, most obviously —
        is escaped as two surrogate halves. Decoding each half on its own yields a
        lone surrogate, which is not a character and cannot be encoded to UTF-8, so
        it would crash the synthesiser rather than being spoken.
        """
        try:
            value = int(digits, 16)
        except ValueError:
            self._high_surrogate = None
            return ""
        high = self._high_surrogate
        self._high_surrogate = None
        if 0xD800 <= value <= 0xDBFF:
            self._high_surrogate = value
            return ""
        if high is not None and 0xDC00 <= value <= 0xDFFF:
            return chr(0x10000 + (high - 0xD800) * 0x400 + (value - 0xDC00))
        if 0xDC00 <= value <= 0xDFFF:
            # An unpaired low surrogate. Dropping it loses one character; emitting
            # it makes the whole reply unencodable.
            return ""
        return chr(value)


class SentenceChunker:
    """Group streamed text into pieces worth speaking.

    A terminator is only treated as one once a following character has arrived and
    turns out to be whitespace, which is what stops "3.5" and "e.g." from being
    split into separate utterances. Short fragments are held back too: synthesising
    "Yes." on its own costs a whole subprocess and sounds clipped.
    """

    def __init__(self, *, minimum_characters: int = 12) -> None:
        self._minimum = minimum_characters
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        pieces: list[str] = []
        while True:
            cut = self._boundary()
            if cut is None:
                break
            piece = self._buffer[:cut].strip()
            self._buffer = self._buffer[cut:]
            if piece:
                pieces.append(piece)
        return pieces

    def flush(self) -> str | None:
        """Whatever is left when the stream ends, terminated or not."""
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None

    def _boundary(self) -> int | None:
        for index, character in enumerate(self._buffer):
            if character in _CLEAR_TERMINATORS:
                if index + 1 >= _MINIMUM_CLEAR_CHARACTERS:
                    return index + 1
                continue
            if character not in _AMBIGUOUS_TERMINATORS:
                continue
            if index + 1 < self._minimum:
                continue
            following = self._buffer[index + 1 : index + 2]
            if not following:
                # Possibly a decimal point whose digit has not arrived yet.
                return None
            if following.isspace():
                return index + 1
        return None
