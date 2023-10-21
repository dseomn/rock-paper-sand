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
"""Code that uses Wikidata's APIs."""

from collections.abc import Generator, Iterable, Sequence
import contextlib
import datetime
import enum
import re
import typing
from typing import Any

from dateutil import relativedelta
import requests
import requests_cache

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import network
from rock_paper_sand.proto import config_pb2

if typing.TYPE_CHECKING:
    import _typeshed


def _min(
    iterable: "Iterable[_typeshed.SupportsRichComparisonT | None]",
    /,
) -> "_typeshed.SupportsRichComparisonT | None":
    return min((x for x in iterable if x is not None), default=None)


def _max(
    iterable: "Iterable[_typeshed.SupportsRichComparisonT | None]",
    /,
) -> "_typeshed.SupportsRichComparisonT | None":
    return max((x for x in iterable if x is not None), default=None)


class _Item(enum.Enum):
    GREGORIAN_CALENDAR = "Q12138"
    PROLEPTIC_GREGORIAN_CALENDAR = "Q1985727"

    @property
    def uri(self) -> str:
        """The canonical URI of the item.

        Note that this is not the URL meant for accessing data about the item,
        but the URI for identifying it.
        """
        return f"http://www.wikidata.org/entity/{self.value}"


class _Property(enum.Enum):
    PUBLICATION_DATE = "P577"
    DATE_OF_FIRST_PERFORMANCE = "P1191"
    START_TIME = "P580"
    END_TIME = "P582"


@contextlib.contextmanager
def requests_session() -> Generator[requests.Session, None, None]:
    """Returns a context manager for a session for Wikidata APIs."""
    with requests_cache.CachedSession(
        **network.requests_cache_defaults(),
    ) as session:
        network.configure_session(session)
        yield session


def _truthy_statements(item: Any, prop: _Property) -> Sequence[Any]:
    # https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format#Truthy_statements
    statements = item["claims"].get(prop.value, ())
    return tuple(
        statement
        for statement in statements
        if statement["rank"] == "preferred"
    ) or tuple(
        statement for statement in statements if statement["rank"] == "normal"
    )


def _parse_snak_time(snak: Any) -> tuple[datetime.datetime, datetime.datetime]:
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
        _Item.GREGORIAN_CALENDAR.uri,
        _Item.PROLEPTIC_GREGORIAN_CALENDAR.uri,
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


def _parse_statement_time(
    statement: Any,
) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """Parses a statement about a time.

    Args:
        statement: Statement to parse.

    Returns:
        Tuple of (earliest possible time, latest possible time). Either or both
        parts may be None if they're unknown or there is no value.
    """
    mainsnak = statement["mainsnak"]
    if mainsnak["datatype"] != "time":
        raise ValueError(
            f"Cannot parse non-time statement as a time: {statement}"
        )
    match mainsnak["snaktype"]:
        case "value":
            return _parse_snak_time(mainsnak)
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


class Api:
    """Wrapper around Wikidata APIs."""

    def __init__(
        self,
        *,
        session: requests.Session,
    ) -> None:
        self._session = session
        self._item_by_qid: dict[str, Any] = {}

    def item(self, qid: str) -> Any:
        """Returns an item in full JSON format."""
        if qid not in self._item_by_qid:
            response = self._session.get(
                f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
            )
            response.raise_for_status()
            self._item_by_qid[qid] = response.json()["entities"][qid]
        return self._item_by_qid[qid]


def _release_status(
    item: Any,
    *,
    now: datetime.datetime,
) -> config_pb2.WikidataFilter.ReleaseStatus.ValueType:
    start = _min(
        (
            _min(_parse_statement_time(statement))
            for statement in _truthy_statements(item, _Property.START_TIME)
        )
    )
    end = _max(
        (
            _max(_parse_statement_time(statement))
            for statement in _truthy_statements(item, _Property.END_TIME)
        )
    )
    if start is not None and now < start:
        return config_pb2.WikidataFilter.ReleaseStatus.UNRELEASED
    elif end is not None and now >= end:
        return config_pb2.WikidataFilter.ReleaseStatus.RELEASED
    elif end is not None and now < end:
        return config_pb2.WikidataFilter.ReleaseStatus.ONGOING
    elif start is not None and end is None:
        return config_pb2.WikidataFilter.ReleaseStatus.ONGOING
    assert start is None and end is None
    for prop in (
        _Property.PUBLICATION_DATE,
        _Property.DATE_OF_FIRST_PERFORMANCE,
    ):
        released = _min(
            (
                _min(_parse_statement_time(statement))
                for statement in _truthy_statements(item, prop)
            )
        )
        if released is None:
            continue
        elif released <= now:
            return config_pb2.WikidataFilter.ReleaseStatus.RELEASED
        else:
            return config_pb2.WikidataFilter.ReleaseStatus.UNRELEASED
    return config_pb2.WikidataFilter.ReleaseStatus.RELEASE_STATUS_UNSPECIFIED


class Filter(media_filter.CachedFilter):
    """Filter based on Wikidata APIs."""

    def __init__(
        self,
        filter_config: config_pb2.WikidataFilter,
        *,
        api: Api,
    ) -> None:
        super().__init__()
        self._config = filter_config
        self._api = api

    def filter_implementation(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        with exceptions.add_note(
            f"While filtering {request.item.debug_description} using Wikidata "
            f"filter config:\n{self._config}"
        ):
            if not request.item.wikidata_qid:
                return media_filter.FilterResult(False)
            item = self._api.item(request.item.wikidata_qid)
            if (
                self._config.release_statuses
                and _release_status(item, now=request.now)
                not in self._config.release_statuses
            ):
                return media_filter.FilterResult(False)
            return media_filter.FilterResult(True)
