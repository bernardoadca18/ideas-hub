"""External authorship contract. Quotes resolve exactly to immutable character ranges."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NarrationBlock(StrictModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[\w-]+$")
    text: str = Field(min_length=1, max_length=100_000)


class Narration(StrictModel):
    blocks: list[NarrationBlock] = Field(min_length=1, max_length=100)


class NarrationAnchor(StrictModel):
    block: str
    start_text: str | None = Field(default=None, min_length=1)
    end_text: str | None = Field(default=None, min_length=1)
    start_char: int | None = Field(default=None, ge=0, strict=True)
    end_char: int | None = Field(default=None, gt=0, strict=True)


class ImportedScene(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[\w-]+$")
    narration_anchor: NarrationAnchor
    visual_intent: str = Field(min_length=1, max_length=10_000)
    prompt: str = Field(min_length=1, max_length=10_000)
    motion_intent: Literal[
        "none",
        "slow_push_in",
        "slow_pull_out",
        "pan_left",
        "pan_right",
        "pan_up",
        "pan_down",
        "pan_left_push_in",
        "pan_right_push_in",
    ] = "none"


class ImportedStoryboard(StrictModel):
    style: dict[str, str] = Field(default_factory=dict)
    continuity: dict[str, str] = Field(default_factory=dict)
    scenes: list[ImportedScene] = Field(min_length=1, max_length=500)


class POVScriptDocument(StrictModel):
    schema_version: Literal["neovids_pov_script_v1"]
    content_locale: Literal["pt-BR", "en-US"]
    title: str = Field(min_length=1, max_length=300)
    narration: Narration
    storyboard: ImportedStoryboard

    @property
    def media(self):
        return None

    @model_validator(mode="after")
    def validate_anchors(self):
        self.canonical_storyboard()
        if not self.title.strip() or any(
            not b.text.strip() for b in self.narration.blocks
        ):
            raise ValueError("storyboard_anchor_invalid: blank narration/title")
        if len(self.model_dump_json().encode()) > 1_000_000:
            raise ValueError("POV script exceeds 1000000 UTF-8 bytes")
        return self

    def canonical_storyboard(self) -> dict:
        blocks = {b.key: (i, b.text) for i, b in enumerate(self.narration.blocks)}
        if len(blocks) != len(self.narration.blocks):
            raise ValueError("storyboard_anchor_invalid: duplicate block key")
        seen = set()
        previous = (-1, 0)
        result = self.storyboard.model_dump(mode="json")
        for scene in result["scenes"]:
            if scene["id"] in seen:
                raise ValueError("storyboard_anchor_invalid: duplicate scene id")
            seen.add(scene["id"])
            anchor = scene["narration_anchor"]
            if anchor["block"] not in blocks:
                raise ValueError("storyboard_anchor_invalid: unknown block")
            order, text = blocks[anchor["block"]]
            start, end = anchor["start_char"], anchor["end_char"]
            quotes = (anchor["start_text"], anchor["end_text"])
            if start is None and end is None and all(quotes):
                offsets = []
                for quote in quotes:
                    occurrences = [
                        i for i in range(len(text)) if text.startswith(quote, i)
                    ]
                    if len(occurrences) != 1:
                        code = (
                            "storyboard_anchor_ambiguous"
                            if occurrences
                            else "storyboard_anchor_invalid"
                        )
                        raise ValueError(f"{code}: quote must occur exactly once")
                    offsets.append(occurrences[0])
                start, end = offsets[0], offsets[1] + len(quotes[1])
            elif start is None or end is None or any(quotes):
                raise ValueError(
                    "storyboard_anchor_invalid: use quotes OR a character range"
                )
            if not 0 <= start < end <= len(text) or not text[start:end].strip():
                raise ValueError("storyboard_anchor_invalid: range outside narration")
            if (order, start) < previous:
                raise ValueError(
                    "storyboard_anchor_invalid: scenes overlap or are unordered"
                )
            previous = (order, end)
            scene["narration_anchor"] = {
                "block": anchor["block"],
                "block_order": order,
                "start_char": start,
                "end_char": end,
                "text": text[start:end],
            }
        result["schema_version"] = "imported_storyboard_v1"
        result["identity"] = hashlib.sha256(
            json.dumps(
                result, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return result
