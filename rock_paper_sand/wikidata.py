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

import collections
from collections.abc import Generator, Iterable, Mapping, Sequence, Set
import contextlib
import dataclasses
import datetime
import functools
import logging
import re
import typing
from typing import Any

from dateutil import relativedelta
import requests
import requests_cache

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import network
from rock_paper_sand import wikidata_value
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


@contextlib.contextmanager
def requests_session() -> Generator[requests.Session, None, None]:
    """Returns a context manager for a session for Wikidata APIs."""
    # TODO(https://github.com/requests-cache/requests-cache/issues/899): Add a
    # flag to manually refresh data, and increase the cache duration
    # significantly.
    with requests_cache.CachedSession(
        **(
            network.requests_cache_defaults()
            | dict[str, Any](
                expire_after=datetime.timedelta(minutes=30),
                cache_control=False,
            )
        ),
    ) as session:
        network.configure_session(session)
        yield session


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


def _label(item: Any, languages: Sequence[str]) -> str | None:
    return _language_keyed_string(item["labels"], languages)


def _description(item: Any, languages: Sequence[str]) -> str | None:
    return _language_keyed_string(item["descriptions"], languages)


def _truthy_statements(
    item: Any, prop: wikidata_value.Property
) -> Sequence[Any]:
    # https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format#Truthy_statements
    statements = item["claims"].get(prop.id, ())
    return tuple(
        statement
        for statement in statements
        if statement["rank"] == "preferred"
    ) or tuple(
        statement for statement in statements if statement["rank"] == "normal"
    )


def _parse_snak_item(snak: Any) -> wikidata_value.Item:
    if snak["snaktype"] != "value":
        raise NotImplementedError(
            f"Cannot parse non-value snak as an item: {snak}"
        )
    if (
        snak["datatype"] != "wikibase-item"
        or snak["datavalue"]["type"] != "wikibase-entityid"
        or snak["datavalue"]["value"]["entity-type"] != "item"
    ):
        raise ValueError(f"Cannot parse non-item snak as a item: {snak}")
    return wikidata_value.Item(snak["datavalue"]["value"]["id"])


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
        wikidata_value.Q_GREGORIAN_CALENDAR.uri,
        wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri,
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


def _parse_sparql_result_item(term: Any) -> wikidata_value.Item:
    if term["type"] != "uri":
        raise ValueError(f"Cannot parse non-uri term as an item: {term}")
    return wikidata_value.Item.from_uri(term["value"])


def _parse_sparql_result_string(term: Any) -> str:
    if term["type"] != "literal":
        raise ValueError(f"Cannot parse non-literal term as a string: {term}")
    if term.keys() & {"datatype", "xml:lang"}:
        raise ValueError(f"Cannot parse non-plain literal as a string: {term}")
    return term["value"]


@dataclasses.dataclass(frozen=True, kw_only=True)
class RelatedMedia:
    """Media or media groups related to a media item.

    Attributes:
        parents: Parents of the item, e.g., a book series that the item is
            included in.
        siblings: Siblings of the item, e.g., sequels and prequels.
        children: Children of the item, e.g., a book that the book series item
            includes.
        loose: More loosely related items, e.g., a work that the item was based
            on but is not necessarily a sequel to.
    """

    parents: Set[wikidata_value.Item]
    siblings: Set[wikidata_value.Item]
    children: Set[wikidata_value.Item]
    loose: Set[wikidata_value.Item]


_PARENT_PROPERTIES = (
    wikidata_value.P_MEDIA_FRANCHISE,
    wikidata_value.P_PART_OF,
    wikidata_value.P_PART_OF_THE_SERIES,
    wikidata_value.P_TAKES_PLACE_IN_FICTIONAL_UNIVERSE,
)
_SIBLING_PROPERTIES = (
    wikidata_value.P_FOLLOWED_BY,
    wikidata_value.P_FOLLOWS,
    wikidata_value.P_SUPPLEMENT_TO,
)
_CHILD_PROPERTIES = (
    wikidata_value.P_FICTIONAL_UNIVERSE_DESCRIBED_IN,
    wikidata_value.P_HAS_PARTS,
)
_LOOSE_PROPERTIES = (
    wikidata_value.P_BASED_ON,
    wikidata_value.P_DERIVATIVE_WORK,
    wikidata_value.P_HAS_SPIN_OFF,
    wikidata_value.P_MANIFESTATION_OF,
    wikidata_value.P_MODIFIED_VERSION_OF,
    wikidata_value.P_PLOT_EXPANDED_IN,
)


class Api:
    """Wrapper around Wikidata APIs."""

    def __init__(
        self,
        *,
        session: requests.Session,
    ) -> None:
        self._session = session
        self._item_by_id: dict[wikidata_value.Item, Any] = {}
        self._item_classes: (
            dict[wikidata_value.Item, Set[wikidata_value.Item]]
        ) = {}
        self._transitive_subclasses: (
            dict[wikidata_value.Item, Set[wikidata_value.Item]]
        ) = {}
        self._related_media: dict[wikidata_value.Item, RelatedMedia] = {}

    def item(self, item_id: wikidata_value.Item) -> Any:
        """Returns an item in full JSON format."""
        if item_id not in self._item_by_id:
            response = self._session.get(
                f"https://www.wikidata.org/wiki/Special:EntityData/{item_id.id}.json"  # pylint: disable=line-too-long
            )
            response.raise_for_status()
            self._item_by_id[item_id] = response.json()["entities"][item_id.id]
        return self._item_by_id[item_id]

    def sparql(self, query: str) -> Any:
        """Returns results from a SPARQL query."""
        logging.debug("SPARQL query:\n%s", query)
        response = self._session.get(
            "https://query.wikidata.org/sparql",
            params=[("query", query)],
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        return response.json()["results"]["bindings"]

    def item_classes(
        self, item_id: wikidata_value.Item
    ) -> Set[wikidata_value.Item]:
        """Returns the classes that the item is an instance of."""
        if item_id not in self._item_classes:
            self._item_classes[item_id] = frozenset(
                _parse_snak_item(statement["mainsnak"])
                for statement in _truthy_statements(
                    self.item(item_id), wikidata_value.P_INSTANCE_OF
                )
            )
        return self._item_classes[item_id]

    def transitive_subclasses(
        self, class_id: wikidata_value.Item
    ) -> Set[wikidata_value.Item]:
        """Returns transitive subclasses of the given class."""
        if class_id not in self._transitive_subclasses:
            subclass_of = wikidata_value.P_SUBCLASS_OF.id
            results = self.sparql(
                "SELECT REDUCED ?class WHERE { "
                f"?class wdt:{subclass_of}* wd:{class_id.id}. "
                "}"
            )
            self._transitive_subclasses[class_id] = frozenset(
                _parse_sparql_result_item(result["class"]) for result in results
            )
        return self._transitive_subclasses[class_id]

    def related_media(self, item_id: wikidata_value.Item) -> RelatedMedia:
        """Returns related media."""
        if item_id not in self._related_media:
            predicate_by_relation = {
                "parent": "|".join(
                    (
                        *(f"wdt:{p.id}" for p in _PARENT_PROPERTIES),
                        *(f"^wdt:{p.id}" for p in _CHILD_PROPERTIES),
                    )
                ),
                "sibling": "|".join(
                    f"wdt:{p.id}|^wdt:{p.id}" for p in _SIBLING_PROPERTIES
                ),
                "child": "|".join(
                    (
                        *(f"wdt:{p.id}" for p in _CHILD_PROPERTIES),
                        *(f"^wdt:{p.id}" for p in _PARENT_PROPERTIES),
                    )
                ),
                "loose": "|".join(
                    f"wdt:{p.id}|^wdt:{p.id}" for p in _LOOSE_PROPERTIES
                ),
            }
            instance_of = wikidata_value.P_INSTANCE_OF.id
            query = " ".join(
                (
                    "SELECT REDUCED ?item ?relation ?class WHERE {",
                    " UNION ".join(
                        (
                            "{ "
                            f"wd:{item_id.id} ({predicate}) ?item. "
                            f'BIND ("{relation}" AS ?relation) '
                            "}"
                        )
                        for relation, predicate in predicate_by_relation.items()
                    ),
                    "FILTER (!wikibase:isSomeValue(?item))",
                    f"OPTIONAL {{ ?item wdt:{instance_of} ?class. }}",
                    "}",
                )
            )
            results = self.sparql(query)
            item_classes: (
                collections.defaultdict[
                    wikidata_value.Item, set[wikidata_value.Item]
                ]
            ) = collections.defaultdict(set)
            items_by_relation: (
                collections.defaultdict[str, set[wikidata_value.Item]]
            ) = collections.defaultdict(set)
            for result in results:
                related_item = _parse_sparql_result_item(result["item"])
                related_item_classes = item_classes[related_item]
                if "class" in result:
                    related_item_classes.add(
                        _parse_sparql_result_item(result["class"])
                    )
                items_by_relation[
                    _parse_sparql_result_string(result["relation"])
                ].add(related_item)
            for related_item, classes in item_classes.items():
                self._item_classes.setdefault(related_item, frozenset(classes))
            related_media = RelatedMedia(
                parents=frozenset(items_by_relation.pop("parent", ())),
                siblings=frozenset(items_by_relation.pop("sibling", ())),
                children=frozenset(items_by_relation.pop("child", ())),
                loose=frozenset(items_by_relation.pop("loose", ())),
            )
            if items_by_relation:
                raise ValueError(
                    "Unexpected media relation types: "
                    f"{list(items_by_relation)}"
                )
            self._related_media[item_id] = related_media
        return self._related_media[item_id]


def _release_status(
    item: Any,
    *,
    now: datetime.datetime,
) -> config_pb2.WikidataFilter.ReleaseStatus.ValueType:
    start = _min(
        (
            _min(_parse_statement_time(statement))
            for statement in _truthy_statements(
                item, wikidata_value.P_START_TIME
            )
        )
    )
    end = _max(
        (
            _max(_parse_statement_time(statement))
            for statement in _truthy_statements(item, wikidata_value.P_END_TIME)
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
        wikidata_value.P_PUBLICATION_DATE,
        wikidata_value.P_DATE_OF_FIRST_PERFORMANCE,
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

    @functools.cached_property
    def _ignored_items(self) -> Set[wikidata_value.Item]:
        return {
            # Subclases of paratext, like preface or introduction, are sometimes
            # used in "has parts" relationships for a book. Since these items
            # are generic (e.g., "introduction") rather than specific to the
            # work (e.g., "introduction to Some Book"), there's not much use in
            # including them. And following them would almost definitely lead to
            # completely unrelated media that just happens to also have an,
            # e.g., introduction.
            *self._api.transitive_subclasses(wikidata_value.Q_PARATEXT),
            # This "fictional universe" seems to contain a lot of other media
            # that doesn't have much in common. See
            # https://en.wikipedia.org/wiki/Tommy_Westphall#Tommy_Westphall_Universe_Hypothesis
            wikidata_value.Q_TOMMY_WESTPHALL_UNIVERSE,
        }

    @functools.cached_property
    def _ignored_classes(self) -> Set[wikidata_value.Item]:
        # Fictional entities (other than fictional universes) can be part of
        # fictional universes, but they're not media items.
        return self._api.transitive_subclasses(
            wikidata_value.Q_FICTIONAL_ENTITY
        ) - self._api.transitive_subclasses(wikidata_value.Q_FICTIONAL_UNIVERSE)

    @functools.cached_property
    def _music_classes(self) -> Set[wikidata_value.Item]:
        return self._api.transitive_subclasses(wikidata_value.Q_RELEASE_GROUP)

    @functools.cached_property
    def _tv_show_classes(self) -> Set[wikidata_value.Item]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_SERIES
        )

    @functools.cached_property
    def _tv_season_classes(self) -> Set[wikidata_value.Item]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_SERIES_SEASON
        )

    @functools.cached_property
    def _tv_season_part_classes(self) -> Set[wikidata_value.Item]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_PART_OF_TELEVISION_SEASON
        )

    @functools.cached_property
    def _tv_season_part_parent_classes(self) -> Set[wikidata_value.Item]:
        return {
            *self._tv_show_classes,
            *self._tv_season_classes,
        }

    @functools.cached_property
    def _tv_episode_classes(self) -> Set[wikidata_value.Item]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_SERIES_EPISODE
        )

    @functools.cached_property
    def _tv_episode_parent_classes(self) -> Set[wikidata_value.Item]:
        return {
            *self._tv_season_part_parent_classes,
            *self._tv_season_part_classes,
        }

    @functools.cached_property
    def _possible_tv_special_classes(self) -> Set[wikidata_value.Item]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_TELEVISION_FILM),
            *self._api.transitive_subclasses(
                wikidata_value.Q_TELEVISION_SPECIAL
            ),
        }

    @functools.cached_property
    def _video_classes(self) -> Set[wikidata_value.Item]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_FILM),
            *self._tv_episode_classes,
        }

    @functools.cached_property
    def _unlikely_to_be_processed_classes(self) -> Set[wikidata_value.Item]:
        return {
            *self._tv_season_classes,
            *self._tv_episode_classes,
        }

    def _is_ignored(
        self,
        item: wikidata_value.Item,
        *,
        request: media_filter.FilterRequest,
        ignored_from_config: set[wikidata_value.Item],
    ) -> bool:
        config_classes_ignore = request.item.wikidata_classes_ignore_recursive
        if item in request.item.wikidata_ignore_items_recursive:
            ignored_from_config.add(item)
            return True
        elif (
            item in self._ignored_items
            or self._api.item_classes(item) & self._ignored_classes
            or any(
                self._api.item_classes(item)
                & self._api.transitive_subclasses(ignored_class)
                for ignored_class in config_classes_ignore
            )
        ):
            return True
        else:
            return False

    def _integral_child_classes(
        self,
    ) -> Iterable[tuple[Set[wikidata_value.Item], Set[wikidata_value.Item]]]:
        """Yields (parent, child) classes that indicate an integral child."""
        yield (self._tv_show_classes, self._tv_season_classes)
        yield (
            self._tv_season_part_parent_classes,
            self._tv_season_part_classes,
        )
        yield (self._video_classes, self._music_classes)
        yield (
            {wikidata_value.Q_LITERARY_WORK},
            {wikidata_value.Q_LITERARY_WORK},
        )

    def _is_integral_child(
        self, parent: wikidata_value.Item, child: wikidata_value.Item
    ) -> bool:
        parent_classes = self._api.item_classes(parent)
        child_classes = self._api.item_classes(child)
        for (
            parent_classes_to_check,
            child_classes_to_check,
        ) in self._integral_child_classes():
            if (
                parent_classes & parent_classes_to_check
                and child_classes & child_classes_to_check
            ):
                return True
        if (
            child_classes & self._tv_episode_classes
            and not child_classes & self._possible_tv_special_classes
            and parent_classes & self._tv_episode_parent_classes
        ):
            return True
        return False

    def _integral_children(
        self, item: wikidata_value.Item, related: RelatedMedia
    ) -> Iterable[wikidata_value.Item]:
        if any(
            self._is_integral_child(parent, item) for parent in related.parents
        ):
            yield item
        yield from (
            child
            for child in related.children
            if self._is_integral_child(item, child)
        )

    def _should_cross_parent_child_border(
        self, parent: wikidata_value.Item, child: wikidata_value.Item
    ) -> bool:
        del child  # Unused.
        parent_classes = self._api.item_classes(parent)
        for collection in (
            wikidata_value.Q_ANTHOLOGY,
            wikidata_value.Q_LIST,
        ):
            if parent_classes & self._api.transitive_subclasses(collection):
                return False
        return True

    def _update_unprocessed(
        self,
        iterable: Iterable[wikidata_value.Item],
        /,
        *,
        current: wikidata_value.Item,
        reached_from: dict[wikidata_value.Item, wikidata_value.Item],
        unprocessed: set[wikidata_value.Item],
        unprocessed_unlikely: set[wikidata_value.Item],
    ) -> None:
        for item in iterable:
            reached_from.setdefault(item, current)
            if (
                self._api.item_classes(item)
                & self._unlikely_to_be_processed_classes
            ):
                unprocessed_unlikely.add(item)
            else:
                unprocessed.add(item)

    def _related_media(
        self, request: media_filter.FilterRequest
    ) -> Set[media_filter.ResultExtra]:
        if request.item.has_parent:
            return frozenset()
        items_from_config = request.item.all_wikidata_items_recursive
        assert request.item.wikidata_item is not None  # Already checked.
        reached_from: dict[wikidata_value.Item, wikidata_value.Item] = {}
        ignored_from_config: set[wikidata_value.Item] = set()
        unprocessed: set[wikidata_value.Item] = {request.item.wikidata_item}
        unprocessed_unlikely: set[wikidata_value.Item] = set()
        processed: set[wikidata_value.Item] = set()
        loose: set[wikidata_value.Item] = set()
        integral_children: set[wikidata_value.Item] = set()
        is_ignored = functools.partial(
            self._is_ignored,
            request=request,
            ignored_from_config=ignored_from_config,
        )
        while unprocessed or unprocessed_unlikely:
            if len(unprocessed) + len(processed) > 1000:
                raise ValueError(
                    "Too many related media items reached from "
                    f"{request.item.wikidata_item}:\n"
                    + "\n".join(
                        f"  {key} reached from {value}"
                        for key, value in reached_from.items()
                    )
                )
            current = (
                unprocessed.pop() if unprocessed else unprocessed_unlikely.pop()
            )
            processed.add(current)
            related = self._api.related_media(current)
            integral_children.update(self._integral_children(current, related))
            update_unprocessed = functools.partial(
                self._update_unprocessed,
                current=current,
                reached_from=reached_from,
                unprocessed=unprocessed,
                unprocessed_unlikely=unprocessed_unlikely,
            )
            update_unprocessed(
                parent
                for parent in related.parents
                if parent not in processed
                and self._should_cross_parent_child_border(parent, current)
                and not is_ignored(parent)
            )
            update_unprocessed(
                sibling
                for sibling in related.siblings
                if sibling not in processed and not is_ignored(sibling)
            )
            update_unprocessed(
                child
                for child in related.children
                if child not in processed
                and self._should_cross_parent_child_border(current, child)
                and not is_ignored(child)
            )
            loose.update(
                loose_item
                for loose_item in related.loose
                if not is_ignored(loose_item)
            )
            update_unprocessed(
                loose_item
                for loose_item in related.loose
                if loose_item in items_from_config
                and loose_item not in processed
                and not is_ignored(loose_item)
            )
            unprocessed -= integral_children
            unprocessed_unlikely -= integral_children
        return {
            *(
                media_filter.ResultExtraString(f"related item: {item}")
                for item in processed - items_from_config - integral_children
            ),
            *(
                media_filter.ResultExtraString(f"loosely-related item: {item}")
                for item in (
                    loose - processed - items_from_config - integral_children
                )
            ),
            *(
                media_filter.ResultExtraString(
                    "item in config file that's not related to "
                    f"{request.item.wikidata_item}: {item}"
                )
                for item in items_from_config - processed - loose
            ),
            *(
                media_filter.ResultExtraString(
                    f"item configured to be ignored, but not found: {item}"
                )
                for item in (
                    request.item.wikidata_ignore_items_recursive
                    - ignored_from_config
                )
            ),
        }

    def filter_implementation(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        with exceptions.add_note(
            f"While filtering {request.item.debug_description} using Wikidata "
            f"filter config:\n{self._config}"
        ):
            if request.item.wikidata_item is None:
                return media_filter.FilterResult(False)
            extra_information: set[media_filter.ResultExtra] = set()
            if self._config.release_statuses:
                item = self._api.item(request.item.wikidata_item)
                if (
                    _release_status(item, now=request.now)
                    not in self._config.release_statuses
                ):
                    return media_filter.FilterResult(False)
            if self._config.HasField("related_media"):
                related_media_extra = self._related_media(request)
                if not related_media_extra:
                    return media_filter.FilterResult(False)
                extra_information.update(related_media_extra)
            return media_filter.FilterResult(True, extra=extra_information)
