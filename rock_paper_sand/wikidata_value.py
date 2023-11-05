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


def _parse_id(
    value: str,
    *,
    prefixes: Collection[str] = ("",),
    letter: str,
) -> str:
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

    def __post_init__(self) -> None:
        _parse_id(self.id, letter="Q")

    def __str__(self) -> str:
        return f"{_ITEM_PREFIX_FOR_HUMAN}{self.id}"

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

    @classmethod
    def from_uri(cls, value: str) -> Self:
        """Returns the item parsed from its canonical URI."""
        return cls(
            _parse_id(value, prefixes=(_ITEM_PREFIX_CANONICAL_URI,), letter="Q")
        )


_i = Item.from_string
Q_ANTHOLOGY = _i("https://www.wikidata.org/wiki/Q105420")
Q_FILM = _i("https://www.wikidata.org/wiki/Q11424")
Q_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q12138")
Q_LIST = _i("https://www.wikidata.org/wiki/Q12139612")
Q_LITERARY_WORK = _i("https://www.wikidata.org/wiki/Q7725634")
Q_PARATEXT = _i("https://www.wikidata.org/wiki/Q853520")
Q_PROLEPTIC_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q1985727")
Q_RELEASE_GROUP = _i("https://www.wikidata.org/wiki/Q108346082")
Q_TELEVISION_FILM = _i("https://www.wikidata.org/wiki/Q506240")
Q_TELEVISION_SERIES = _i("https://www.wikidata.org/wiki/Q5398426")
Q_TELEVISION_SERIES_EPISODE = _i("https://www.wikidata.org/wiki/Q21191270")
Q_TELEVISION_SERIES_SEASON = _i("https://www.wikidata.org/wiki/Q3464665")
Q_TELEVISION_SPECIAL = _i("https://www.wikidata.org/wiki/Q1261214")
del _i

_PROPERTY_PREFIX_FOR_HUMAN = "https://www.wikidata.org/wiki/Property:"


@dataclasses.dataclass(frozen=True)
class Property:
    """Wikidata property.

    Attributes:
        id: ID of the item, e.g., "P580".
    """

    id: str

    def __post_init__(self) -> None:
        _parse_id(self.id, letter="P")

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Returns the property parsed from a string."""
        return cls(
            _parse_id(
                value,
                prefixes=("", _PROPERTY_PREFIX_FOR_HUMAN),
                letter="P",
            )
        )


_p = Property.from_string
P_BASED_ON = _p("https://www.wikidata.org/wiki/Property:P144")
P_DATE_OF_FIRST_PERFORMANCE = _p("https://www.wikidata.org/wiki/Property:P1191")
P_DERIVATIVE_WORK = _p("https://www.wikidata.org/wiki/Property:P4969")
P_END_TIME = _p("https://www.wikidata.org/wiki/Property:P582")
P_FICTIONAL_UNIVERSE_DESCRIBED_IN = _p(
    "https://www.wikidata.org/wiki/Property:P1445"
)
P_FOLLOWED_BY = _p("https://www.wikidata.org/wiki/Property:P156")
P_FOLLOWS = _p("https://www.wikidata.org/wiki/Property:P155")
P_HAS_PARTS = _p("https://www.wikidata.org/wiki/Property:P527")
P_INSTANCE_OF = _p("https://www.wikidata.org/wiki/Property:P31")
P_PART_OF = _p("https://www.wikidata.org/wiki/Property:P361")
P_PART_OF_THE_SERIES = _p("https://www.wikidata.org/wiki/Property:P179")
P_PUBLICATION_DATE = _p("https://www.wikidata.org/wiki/Property:P577")
P_START_TIME = _p("https://www.wikidata.org/wiki/Property:P580")
P_SUBCLASS_OF = _p("https://www.wikidata.org/wiki/Property:P279")
P_TAKES_PLACE_IN_FICTIONAL_UNIVERSE = _p(
    "https://www.wikidata.org/wiki/Property:P1434"
)
del _p
