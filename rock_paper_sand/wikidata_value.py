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
"""Representation of Wikidata values.

See https://www.mediawiki.org/wiki/Wikibase/DataModel
"""

from collections.abc import Collection
import dataclasses
import re
from typing import Self


def _parse_id(value: str, *, prefixes: Collection[str], letter: str) -> str:
    """Returns a parsed Wikidata ID.

    Args:
        value: String to parse.
        prefixes: Valid prefixes before the ID, e.g.,
            "https://www.wikidata.org/wiki/" for an item.
        letter: Which letter the ID starts with, e.g., "Q" for an item.
    """
    match = re.fullmatch(
        r"(?P<prefix>.*)(?P<id>(?P<letter>[A-Z])[0-9]+)", value
    )
    if (
        match is None
        or match.group("prefix") not in prefixes
        or match.group("letter") != letter
    ):
        recognized_forms = [f"{prefix}{letter}123" for prefix in prefixes]
        raise ValueError(
            f"Wikidata IRI or ID {value!r} is not in one of the recognized "
            f"forms: {recognized_forms}"
        )
    return match.group("id")


_ITEM_PREFIX_FOR_HUMAN = "https://www.wikidata.org/wiki/"
_ITEM_PREFIX_CANONICAL_URI = "http://www.wikidata.org/entity/"


@dataclasses.dataclass(frozen=True)
class Item:
    """Wikidata item.

    Attributes:
        id: QID of the item, e.g., "Q3107329".
    """

    id: str

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Returns the item parsed from a string."""
        return cls(
            _parse_id(value, prefixes=("", _ITEM_PREFIX_FOR_HUMAN), letter="Q")
        )

    @property
    def uri(self) -> str:
        """The canonical URI of the item.

        Note that this is not the URL meant for accessing data about the item,
        but the URI for identifying it.
        """
        return f"{_ITEM_PREFIX_CANONICAL_URI}{self.id}"


Q_GREGORIAN_CALENDAR = Item("Q12138")
Q_PROLEPTIC_GREGORIAN_CALENDAR = Item("Q1985727")
