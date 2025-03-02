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

import abc
from collections.abc import Collection, Mapping, Sequence
import dataclasses
import datetime
import re
from typing import Any, Self

from dateutil import relativedelta


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


_ENTITY_PREFIX_CANONICAL_URI = "http://www.wikidata.org/entity/"


@dataclasses.dataclass(frozen=True)
class EntityRef(abc.ABC):
    """Reference (ID/URI) to a Wikidata entity.

    Attributes:
        id: ID of the entity, e.g., "Q3107329" for an item or "P580" for a
            property.
    """

    id: str

    @classmethod
    @abc.abstractmethod
    def letter(cls) -> str:
        """Returns which letter the ID starts with, e.g., "Q" for an item."""
        raise NotImplementedError()

    @classmethod
    @abc.abstractmethod
    def human_readable_url_prefix(cls) -> str:
        """Returns the prefix before the ID for a human-readable URL."""
        raise NotImplementedError()

    def __post_init__(self) -> None:
        _parse_id(self.id, letter=self.letter())  # Validate the ID.

    def __str__(self) -> str:
        return f"{self.human_readable_url_prefix()}{self.id}"

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Returns the entity ref parsed from a string."""
        return cls(
            _parse_id(
                value,
                prefixes=("", cls.human_readable_url_prefix()),
                letter=cls.letter(),
            )
        )

    @property
    def uri(self) -> str:
        """The canonical URI of the entity.

        Note that this is not the URL meant for accessing data about the entity,
        but the URI for identifying it.
        """
        return f"{_ENTITY_PREFIX_CANONICAL_URI}{self.id}"

    @classmethod
    def from_uri(cls, value: str) -> Self:
        """Returns the entity ref parsed from its canonical URI."""
        return cls(
            _parse_id(
                value,
                prefixes=(_ENTITY_PREFIX_CANONICAL_URI,),
                letter=cls.letter(),
            )
        )


class ItemRef(EntityRef):
    """Reference (ID/URI) to a Wikidata item."""

    @classmethod
    def letter(cls) -> str:
        """See base class."""
        return "Q"

    @classmethod
    def human_readable_url_prefix(cls) -> str:
        """See base class."""
        return "https://www.wikidata.org/wiki/"


_i = ItemRef.from_string
Q_ANTHOLOGY = _i("https://www.wikidata.org/wiki/Q105420")
Q_ANTHOLOGY_FILM = _i("https://www.wikidata.org/wiki/Q336144")
Q_BOX_OFFICE = _i("https://www.wikidata.org/wiki/Q21707777")
Q_CLASS_OF_FICTIONAL_ENTITIES = _i("https://www.wikidata.org/wiki/Q15831596")
Q_COLLECTION_OF_LITERARY_WORKS = _i("https://www.wikidata.org/wiki/Q108329152")
Q_FICTIONAL_ENTITY = _i("https://www.wikidata.org/wiki/Q14897293")
Q_FICTIONAL_UNIVERSE = _i("https://www.wikidata.org/wiki/Q559618")
Q_FILM = _i("https://www.wikidata.org/wiki/Q11424")
Q_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q12138")
Q_LIST = _i("https://www.wikidata.org/wiki/Q12139612")
Q_LITERARY_WORK = _i("https://www.wikidata.org/wiki/Q7725634")
Q_MUSICAL_WORK = _i("https://www.wikidata.org/wiki/Q2188189")
Q_NOVELLA = _i("https://www.wikidata.org/wiki/Q149537")
Q_OMNIVERSE = _i("https://www.wikidata.org/wiki/Q116503898")
Q_PARATEXT = _i("https://www.wikidata.org/wiki/Q853520")
Q_PART_OF_TELEVISION_SEASON = _i("https://www.wikidata.org/wiki/Q93992677")
Q_PLACEHOLDER_NAME = _i("https://www.wikidata.org/wiki/Q1318274")
Q_PROLEPTIC_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q1985727")
Q_RELEASE_GROUP = _i("https://www.wikidata.org/wiki/Q108346082")
Q_SCENE = _i("https://www.wikidata.org/wiki/Q282939")
Q_SEGMENT_OF_A_TELEVISION_EPISODE = _i(
    "https://www.wikidata.org/wiki/Q29555881"
)
Q_SHORT_STORY = _i("https://www.wikidata.org/wiki/Q49084")
Q_TELEVISION_FILM = _i("https://www.wikidata.org/wiki/Q506240")
Q_TELEVISION_PILOT = _i("https://www.wikidata.org/wiki/Q653916")
Q_TELEVISION_SERIES = _i("https://www.wikidata.org/wiki/Q5398426")
Q_TELEVISION_SERIES_EPISODE = _i("https://www.wikidata.org/wiki/Q21191270")
Q_TELEVISION_SERIES_SEASON = _i("https://www.wikidata.org/wiki/Q3464665")
Q_TELEVISION_SPECIAL = _i("https://www.wikidata.org/wiki/Q1261214")
Q_TOMMY_WESTPHALL_UNIVERSE = _i("https://www.wikidata.org/wiki/Q95410310")
Q_WEB_SERIES = _i("https://www.wikidata.org/wiki/Q526877")
Q_WEB_SERIES_EPISODE = _i("https://www.wikidata.org/wiki/Q1464125")
Q_WEB_SERIES_SEASON = _i("https://www.wikidata.org/wiki/Q61704031")
Q_WIKIMEDIA_PAGE_OUTSIDE_THE_MAIN_KNOWLEDGE_TREE = _i(
    "https://www.wikidata.org/wiki/Q17379835"
)
del _i


class PropertyRef(EntityRef):
    """Reference (ID/URI) to a Wikidata property."""

    @classmethod
    def letter(cls) -> str:
        """See base class."""
        return "P"

    @classmethod
    def human_readable_url_prefix(cls) -> str:
        """See base class."""
        return "https://www.wikidata.org/wiki/Property:"


_p = PropertyRef.from_string
P_BASED_ON = _p("https://www.wikidata.org/wiki/Property:P144")
P_DATE_OF_FIRST_PERFORMANCE = _p("https://www.wikidata.org/wiki/Property:P1191")
P_DERIVATIVE_WORK = _p("https://www.wikidata.org/wiki/Property:P4969")
P_END_TIME = _p("https://www.wikidata.org/wiki/Property:P582")
P_FICTIONAL_UNIVERSE_DESCRIBED_IN = _p(
    "https://www.wikidata.org/wiki/Property:P1445"
)
P_FOLLOWED_BY = _p("https://www.wikidata.org/wiki/Property:P156")
P_FOLLOWS = _p("https://www.wikidata.org/wiki/Property:P155")
P_FORM_OF_CREATIVE_WORK = _p("https://www.wikidata.org/wiki/Property:P7937")
P_HAS_PARTS = _p("https://www.wikidata.org/wiki/Property:P527")
P_HAS_SPIN_OFF = _p("https://www.wikidata.org/wiki/Property:P2512")
P_INSTANCE_OF = _p("https://www.wikidata.org/wiki/Property:P31")
P_MANIFESTATION_OF = _p("https://www.wikidata.org/wiki/Property:P1557")
P_MEDIA_FRANCHISE = _p("https://www.wikidata.org/wiki/Property:P8345")
P_MODIFIED_VERSION_OF = _p("https://www.wikidata.org/wiki/Property:P5059")
P_PART_OF = _p("https://www.wikidata.org/wiki/Property:P361")
P_PART_OF_THE_SERIES = _p("https://www.wikidata.org/wiki/Property:P179")
P_PLACE_OF_PUBLICATION = _p("https://www.wikidata.org/wiki/Property:P291")
P_PLOT_EXPANDED_IN = _p("https://www.wikidata.org/wiki/Property:P5940")
P_PUBLICATION_DATE = _p("https://www.wikidata.org/wiki/Property:P577")
P_SEASON = _p("https://www.wikidata.org/wiki/Property:P4908")
P_SERIES_ORDINAL = _p("https://www.wikidata.org/wiki/Property:P1545")
P_START_TIME = _p("https://www.wikidata.org/wiki/Property:P580")
P_SUBCLASS_OF = _p("https://www.wikidata.org/wiki/Property:P279")
P_SUPPLEMENT_TO = _p("https://www.wikidata.org/wiki/Property:P9234")
P_TAKES_PLACE_IN_FICTIONAL_UNIVERSE = _p(
    "https://www.wikidata.org/wiki/Property:P1434"
)
del _p


def _language_keyed_string(
    mapping: Mapping[str, Any],
    languages: Sequence[str],
) -> str | None:
    # https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html#json_fingerprint
    for language in languages:
        if language in mapping:
            return mapping[language]["value"]
        for other_language, record in mapping.items():
            if other_language.startswith(f"{language}-"):
                return record["value"]
    return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Snak:
    """Snak.

    Attributes:
        json: See
            https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html#json_snaks
    """

    json: Any

    def item_value(self) -> ItemRef:
        """Returns the snak's item value."""
        if self.json["snaktype"] != "value":
            raise NotImplementedError(
                f"Cannot parse non-value snak as an item: {self.json}"
            )
        if (
            self.json["datatype"] != "wikibase-item"
            or self.json["datavalue"]["type"] != "wikibase-entityid"
            or self.json["datavalue"]["value"]["entity-type"] != "item"
        ):
            raise ValueError(
                f"Cannot parse non-item snak as an item: {self.json}"
            )
        return ItemRef(self.json["datavalue"]["value"]["id"])

    def string_value(self) -> str:
        """Returns the snak's string value."""
        if self.json["snaktype"] != "value":
            raise NotImplementedError(
                f"Cannot parse non-value snak as a string: {self.json}"
            )
        if (
            self.json["datatype"] != "string"
            or self.json["datavalue"]["type"] != "string"
        ):
            raise ValueError(
                f"Cannot parse non-string snak as a string: {self.json}"
            )
        return self.json["datavalue"]["value"]

    def time_value(self) -> tuple[datetime.datetime, datetime.datetime]:
        """Returns (earliest possible time, latest possible time)."""
        if self.json["snaktype"] != "value":
            raise NotImplementedError(
                f"Cannot parse non-value snak as a time: {self.json}"
            )
        if (
            self.json["datatype"] != "time"
            or self.json["datavalue"]["type"] != "time"
        ):
            raise ValueError(
                f"Cannot parse non-time snak as a time: {self.json}"
            )
        value = self.json["datavalue"]["value"]
        if value["calendarmodel"] not in (
            Q_GREGORIAN_CALENDAR.uri,
            Q_PROLEPTIC_GREGORIAN_CALENDAR.uri,
        ):
            raise NotImplementedError(
                f"Cannot parse non-Gregorian time: {self.json}"
            )
        if value["timezone"] != 0:
            raise NotImplementedError(f"Cannot parse non-UTC time: {self.json}")
        try:
            precision = {
                7: relativedelta.relativedelta(years=100),
                8: relativedelta.relativedelta(years=10),
                9: relativedelta.relativedelta(years=1),
                10: relativedelta.relativedelta(months=1),
                11: relativedelta.relativedelta(days=1),
            }[value["precision"]]
        except KeyError:
            raise NotImplementedError(
                f"Cannot parse time's precision: {self.json}"
            ) from None
        match = re.fullmatch(
            (
                r"\+([0-9]{4})-([0-9]{2})-([0-9]{2})"
                r"T"
                r"([0-9]{2}):([0-9]{2}):([0-9]{2})Z"
            ),
            value["time"],
        )
        if match is None:
            raise ValueError(f"Cannot parse time: {self.json}")
        year, month, day, hour, minute, second = map(int, match.groups())
        base = datetime.datetime(
            year=year,
            month=month or 1,
            day=day or 1,
            hour=hour,
            minute=minute,
            second=second,
            tzinfo=datetime.timezone.utc,
        )
        earliest = base - value.get("before", 0) * precision
        latest = (
            base
            + value.get("after", 0) * precision
            + precision
            - datetime.timedelta(microseconds=1)
        )
        return earliest, latest


@dataclasses.dataclass(frozen=True, kw_only=True)
class Statement:
    """Statement.

    Attributes:
        json: See
            https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html#json_statements
    """

    json: Any

    def mainsnak(self) -> Snak:
        """Returns the main snak."""
        return Snak(json=self.json["mainsnak"])

    def qualifiers(self, property_ref: PropertyRef) -> Collection[Snak]:
        """Returns qualifiers for the given property."""
        return tuple(
            Snak(json=snak)
            for snak in self.json.get("qualifiers", {}).get(property_ref.id, ())
        )

    def time_value(
        self,
    ) -> tuple[datetime.datetime | None, datetime.datetime | None]:
        """Returns the statement as time values.

        Returns:
            Tuple of (earliest possible time, latest possible time). Either or
            both parts may be None if they're unknown or there is no value.
        """
        mainsnak = self.mainsnak()
        if mainsnak.json["datatype"] != "time":
            raise ValueError(
                f"Cannot parse non-time statement as a time: {self.json}"
            )
        match mainsnak.json["snaktype"]:
            case "value":
                return mainsnak.time_value()
            case "somevalue":
                noop_qualifiers = {
                    P_PLACE_OF_PUBLICATION.id,
                }
                if self.json.get("qualifiers", {}).keys() - noop_qualifiers:
                    raise NotImplementedError(
                        "Cannot parse somevalue time with unsupported "
                        f"qualifiers: {self.json}"
                    )
                else:
                    return (None, None)
            case "novalue":
                return (None, None)
            case _:
                raise ValueError(
                    f"Unexpected snaktype in time statement: {self.json}"
                )


@dataclasses.dataclass(frozen=True, kw_only=True)
class Entity:
    """Data about an entity.

    Attributes:
        json_full: JSON data about the entity, full flavor. See
            https://www.wikidata.org/wiki/Wikidata:Data_access#Linked_Data_Interface_(URI)
            for how to get the data and
            https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html
            for the format.
    """

    json_full: Any

    def label(self, languages: Sequence[str]) -> str | None:
        """Returns a label in the first matching language, or None."""
        return _language_keyed_string(self.json_full["labels"], languages)

    def description(self, languages: Sequence[str]) -> str | None:
        """Returns a description in the first matching language, or None."""
        return _language_keyed_string(self.json_full["descriptions"], languages)

    def truthy_statements(
        self, property_ref: PropertyRef
    ) -> Collection[Statement]:
        # https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format#Truthy_statements
        statements = self.json_full["claims"].get(property_ref.id, ())
        return tuple(
            Statement(json=statement)
            for statement in statements
            if statement["rank"] == "preferred"
        ) or tuple(
            Statement(json=statement)
            for statement in statements
            if statement["rank"] == "normal"
        )


# https://www.w3.org/TR/2013/REC-sparql11-results-json-20130321/#select-encode-terms
SparqlTerm = Mapping[str, Any]


def parse_sparql_term_item(term: SparqlTerm) -> ItemRef:
    """Returns an item value from a term."""
    if term["type"] != "uri":
        raise ValueError(f"Cannot parse non-uri term as an item: {term}")
    return ItemRef.from_uri(term["value"])


def parse_sparql_term_string(term: SparqlTerm) -> str:
    """Returns an string value from a term."""
    if term["type"] != "literal":
        raise ValueError(f"Cannot parse non-literal term as a string: {term}")
    if term.keys() & {"datatype", "xml:lang"}:
        raise ValueError(f"Cannot parse non-plain literal as a string: {term}")
    return term["value"]
