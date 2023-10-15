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

from collections.abc import Iterable, Sequence
import dataclasses
from typing import Self
import uuid

from rock_paper_sand import exceptions
from rock_paper_sand import multi_level_set
from rock_paper_sand.proto import config_pb2


@dataclasses.dataclass(frozen=True, kw_only=True)
class MediaItem:
    """Media item.

    Attributes:
        id: Unique ID of the media item. This is not stable across runs of the
            program, so it should not be stored anywhere or shown to the user.
            It's designed for caching filter results in memory.
        debug_description: Description of the media item for use in logs or
            exceptions.
        proto: Proto from the config file.
        fully_qualified_name: Name, including names of parents.
        done: Parsed proto.done field.
        parts: Parsed proto.parts field.
    """

    id: str = dataclasses.field(
        default_factory=lambda: str(uuid.uuid4()),
        repr=False,
    )
    debug_description: str
    proto: config_pb2.MediaItem
    fully_qualified_name: str
    done: multi_level_set.MultiLevelSet
    parts: Sequence["MediaItem"]

    @classmethod
    def from_config(
        cls,
        proto: config_pb2.MediaItem,
        *,
        index: Sequence[int] = (),
        parent_fully_qualified_name: str | None = None,
    ) -> Self:
        """Parses from a config proto.

        Args:
            proto: Config to parse.
            index: Index within the config file. () means it's not from a config
                file. (0,) means it's media[0]. (0, 1, 2) means it's
                media[0].parts[1].parts[2].
            parent_fully_qualified_name: fully_qualified_name of the parent, or
                None if there is no parent.
        """
        fully_qualified_name = (
            proto.name
            if parent_fully_qualified_name is None
            else f"{parent_fully_qualified_name}: {proto.name}"
        )
        parts = tuple(
            cls.from_config(
                part,
                index=(*index, part_index) if index else (),
                parent_fully_qualified_name=fully_qualified_name,
            )
            for part_index, part in enumerate(proto.parts)
        )
        if index:
            path = ".".join(
                (
                    f"media[{index[0]}]",
                    *(f"parts[{part_index}]" for part_index in index[1:]),
                )
            )
        else:
            path = "unknown media item"
        debug_description = f"{path} with name {proto.name!r}"
        with exceptions.add_note(f"In {debug_description}."):
            if not proto.name:
                raise ValueError("The name field is required.")
            return cls(
                debug_description=debug_description,
                proto=proto,
                fully_qualified_name=fully_qualified_name,
                done=multi_level_set.MultiLevelSet.from_string(proto.done),
                parts=parts,
            )


def iter_all_items(media: Iterable[MediaItem]) -> Iterable[MediaItem]:
    """Yields all media items, recursively."""
    for item in media:
        yield item
        yield from iter_all_items(item.parts)
