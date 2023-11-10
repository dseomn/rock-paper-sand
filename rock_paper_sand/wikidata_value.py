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
from typing import Any, NewType, Self

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
Q_FICTIONAL_ENTITY = _i("https://www.wikidata.org/wiki/Q14897293")
Q_FICTIONAL_UNIVERSE = _i("https://www.wikidata.org/wiki/Q559618")
Q_FILM = _i("https://www.wikidata.org/wiki/Q11424")
Q_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q12138")
Q_LIST = _i("https://www.wikidata.org/wiki/Q12139612")
Q_LITERARY_WORK = _i("https://www.wikidata.org/wiki/Q7725634")
Q_PARATEXT = _i("https://www.wikidata.org/wiki/Q853520")
Q_PART_OF_TELEVISION_SEASON = _i("https://www.wikidata.org/wiki/Q93992677")
Q_PROLEPTIC_GREGORIAN_CALENDAR = _i("https://www.wikidata.org/wiki/Q1985727")
Q_RELEASE_GROUP = _i("https://www.wikidata.org/wiki/Q108346082")
Q_TELEVISION_FILM = _i("https://www.wikidata.org/wiki/Q506240")
Q_TELEVISION_SERIES = _i("https://www.wikidata.org/wiki/Q5398426")
Q_TELEVISION_SERIES_EPISODE = _i("https://www.wikidata.org/wiki/Q21191270")
Q_TELEVISION_SERIES_SEASON = _i("https://www.wikidata.org/wiki/Q3464665")
Q_TELEVISION_SPECIAL = _i("https://www.wikidata.org/wiki/Q1261214")
Q_TOMMY_WESTPHALL_UNIVERSE = _i("https://www.wikidata.org/wiki/Q95410310")
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
P_HAS_PARTS = _p("https://www.wikidata.org/wiki/Property:P527")
P_HAS_SPIN_OFF = _p("https://www.wikidata.org/wiki/Property:P2512")
P_INSTANCE_OF = _p("https://www.wikidata.org/wiki/Property:P31")
P_MANIFESTATION_OF = _p("https://www.wikidata.org/wiki/Property:P1557")
P_MEDIA_FRANCHISE = _p("https://www.wikidata.org/wiki/Property:P8345")
P_MODIFIED_VERSION_OF = _p("https://www.wikidata.org/wiki/Property:P5059")
P_PART_OF = _p("https://www.wikidata.org/wiki/Property:P361")
P_PART_OF_THE_SERIES = _p("https://www.wikidata.org/wiki/Property:P179")
P_PLOT_EXPANDED_IN = _p("https://www.wikidata.org/wiki/Property:P5940")
P_PUBLICATION_DATE = _p("https://www.wikidata.org/wiki/Property:P577")
P_START_TIME = _p("https://www.wikidata.org/wiki/Property:P580")
P_SUBCLASS_OF = _p("https://www.wikidata.org/wiki/Property:P279")
P_SUPPLEMENT_TO = _p("https://www.wikidata.org/wiki/Property:P9234")
P_TAKES_PLACE_IN_FICTIONAL_UNIVERSE = _p(
    "https://www.wikidata.org/wiki/Property:P1434"
)
del _p

Snak = NewType("Snak", Mapping[str, Any])
Statement = NewType("Statement", Mapping[str, Any])


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


def statement_qualifiers(
    statement: Statement, property_ref: PropertyRef
) -> Collection[Snak]:
    """Returns property_ref's qualifiers of statement."""
    return tuple(
        map(Snak, statement.get("qualifiers", {}).get(property_ref.id, ()))
    )


def parse_snak_item(snak: Snak) -> ItemRef:
    """Returns an item value from a snak."""
    if snak["snaktype"] != "value":
        raise NotImplementedError(
            f"Cannot parse non-value snak as an item: {snak}"
        )
    if (
        snak["datatype"] != "wikibase-item"
        or snak["datavalue"]["type"] != "wikibase-entityid"
        or snak["datavalue"]["value"]["entity-type"] != "item"
    ):
        raise ValueError(f"Cannot parse non-item snak as an item: {snak}")
    return ItemRef(snak["datavalue"]["value"]["id"])


def parse_snak_string(snak: Snak) -> str:
    """Returns a string value from a snak."""
    if snak["snaktype"] != "value":
        raise NotImplementedError(
            f"Cannot parse non-value snak as a string: {snak}"
        )
    if snak["datatype"] != "string" or snak["datavalue"]["type"] != "string":
        raise ValueError(f"Cannot parse non-string snak as a string: {snak}")
    return snak["datavalue"]["value"]


def parse_snak_time(snak: Snak) -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (earliest possible time, latest possible time) of a time snak."""
    # https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html#json_datavalues_time
    if snak["snaktype"] != "value":
        raise NotImplementedError(
            f"Cannot parse non-value snak as a time: {snak}"
        )
    if snak["datatype"] != "time" or snak["datavalue"]["type"] != "time":
        raise ValueError(f"Cannot parse non-time snak as a time: {snak}")
    value = snak["datavalue"]["value"]
    if value["calendarmodel"] not in (
        Q_GREGORIAN_CALENDAR.uri,
        Q_PROLEPTIC_GREGORIAN_CALENDAR.uri,
    ):
        raise NotImplementedError(f"Cannot parse non-Gregorian time: {snak}")
    if value["timezone"] != 0:
        raise NotImplementedError(f"Cannot parse non-UTC time: {snak}")
    if value.get("before", 0) != 0 or value.get("after", 0) != 0:
        raise NotImplementedError(
            f"Cannot parse time with uncertainty range: {snak}"
        )
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
            f"Cannot parse time's precision: {snak}"
        ) from None
    match = re.fullmatch(
        r"\+([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z",
        value["time"],
    )
    if match is None:
        raise ValueError(f"Cannot parse time: {snak}")
    year, month, day, hour, minute, second = map(int, match.groups())
    earliest = datetime.datetime(
        year=year,
        month=month or 1,
        day=day or 1,
        hour=hour,
        minute=minute,
        second=second,
        tzinfo=datetime.timezone.utc,
    )
    latest = earliest + precision - datetime.timedelta(microseconds=1)
    return earliest, latest


def parse_statement_time(
    statement: Statement,
) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """Parses a statement about a time.

    Args:
        statement: Statement to parse.

    Returns:
        Tuple of (earliest possible time, latest possible time). Either or both
        parts may be None if they're unknown or there is no value.
    """
    # TODO(https://github.com/pylint-dev/pylint/issues/4944): Remove
    # unsubscriptable-object disables.
    mainsnak = Snak(statement["mainsnak"])
    if mainsnak["datatype"] != "time":  # pylint: disable=unsubscriptable-object
        raise ValueError(
            f"Cannot parse non-time statement as a time: {statement}"
        )
    match mainsnak["snaktype"]:  # pylint: disable=unsubscriptable-object
        case "value":
            return parse_snak_time(mainsnak)
        case "somevalue":
            if statement.get("qualifiers", {}):
                raise NotImplementedError(
                    f"Cannot parse somevalue time with qualifiers: {statement}"
                )
            else:
                return (None, None)
        case "novalue":
            return (None, None)
        case _:
            raise ValueError(
                f"Unexpected snaktype in time statement: {statement}"
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
            Statement(statement)
            for statement in statements
            if statement["rank"] == "preferred"
        ) or tuple(
            Statement(statement)
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
