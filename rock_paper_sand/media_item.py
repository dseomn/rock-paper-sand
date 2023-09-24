# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Media items."""

from collections.abc import Sequence
import dataclasses
from typing import Self
import uuid

from rock_paper_sand import multi_level_set
from rock_paper_sand.proto import config_pb2


@dataclasses.dataclass(frozen=True, kw_only=True)
class MediaItem:
    """Media item.

    Attributes:
        id: Unique ID of the media item. This is not stable across runs of the
            program, so it should not be stored anywhere or shown to the user.
            It's designed for caching filter results in memory.
        proto: Proto from the config file.
        done: Parsed proto.done field.
        parts: Parsed proto.parts field.
    """

    id: str = dataclasses.field(
        default_factory=lambda: str(uuid.uuid4()),
        repr=False,
    )
    proto: config_pb2.MediaItem
    done: multi_level_set.MultiLevelSet
    parts: Sequence["MediaItem"]

    @classmethod
    def from_config(cls, proto: config_pb2.MediaItem) -> Self:
        """Parses from a config proto."""
        return cls(
            proto=proto,
            done=multi_level_set.MultiLevelSet.from_string(proto.done),
            parts=tuple(map(cls.from_config, proto.parts)),
        )
