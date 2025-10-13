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
from collections.abc import Generator, Iterable, Sequence, Set
import contextlib
import dataclasses
import datetime
import enum
import functools
import itertools
import logging
import typing
from typing import Any

from absl import flags
import requests
import requests_cache

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import network
from rock_paper_sand import wikidata_value
from rock_paper_sand.proto import config_pb2

if typing.TYPE_CHECKING:
    import _typeshed

_WIKIDATA_REFRESH = flags.DEFINE_bool(
    "wikidata_refresh",
    default=False,
    help="Use fresh data from wikidata, instead of cached.",
)


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
    with requests_cache.CachedSession(
        **(
            network.requests_cache_defaults()
            | dict[str, Any](
                expire_after=datetime.timedelta(hours=20),
                cache_control=False,
            )
        ),
    ) as session:
        network.configure_session(session)
        if _WIKIDATA_REFRESH.value:
            session.headers["Cache-Control"] = "no-cache"
        yield session


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

    parents: Set[wikidata_value.ItemRef]
    siblings: Set[wikidata_value.ItemRef]
    children: Set[wikidata_value.ItemRef]
    loose: Set[wikidata_value.ItemRef]


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


class _RelatedMediaPriority(enum.IntEnum):
    """How likely an item is to be processed for related media.

    Attributes:
        UNLIKELY: Unlikely to be processed. E.g., TV episodes are likely to be
            integral children of TV shows, so they're unlikely to be processed
            any further.
        POSSIBLE: Might or might not be processed. E.g., short stories are
            sometimes integral children of books that have multiple related
            short stories.
        LIKELY: Likely to be processed, because none of the above applies.
    """

    UNLIKELY = enum.auto()
    POSSIBLE = enum.auto()
    LIKELY = enum.auto()


class Api:
    """Wrapper around Wikidata APIs."""

    def __init__(
        self,
        *,
        session: requests.Session,
    ) -> None:
        self._session = session
        self._entity_by_ref: dict[
            wikidata_value.EntityRef, wikidata_value.Entity
        ] = {}
        self._entity_classes: dict[
            wikidata_value.EntityRef, Set[wikidata_value.ItemRef]
        ] = {}
        self._forms_of_creative_work: dict[
            wikidata_value.ItemRef, Set[wikidata_value.ItemRef]
        ] = {}
        self._transitive_subclasses: dict[
            wikidata_value.ItemRef, Set[wikidata_value.ItemRef]
        ] = {}
        self._related_media: dict[wikidata_value.ItemRef, RelatedMedia] = {}

    def entity(
        self, entity_ref: wikidata_value.EntityRef
    ) -> wikidata_value.Entity:
        """Returns an entity."""
        if entity_ref not in self._entity_by_ref:
            response = self._session.get(
                f"https://www.wikidata.org/wiki/Special:EntityData/{entity_ref.id}.json"  # pylint: disable=line-too-long
            )
            response.raise_for_status()
            entities = response.json()["entities"]
            if entity_ref.id not in entities:
                raise ValueError(
                    f"JSON data for {entity_ref} does not contain "
                    f"{entity_ref.id!r}. Maybe it was merged with another "
                    "entity?"
                )
            self._entity_by_ref[entity_ref] = wikidata_value.Entity(
                json_full=entities[entity_ref.id],
            )
        return self._entity_by_ref[entity_ref]

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

    def entity_classes(
        self, entity_ref: wikidata_value.EntityRef
    ) -> Set[wikidata_value.ItemRef]:
        """Returns the classes that the entity is an instance of."""
        if entity_ref not in self._entity_classes:
            self._entity_classes[entity_ref] = frozenset(
                statement.mainsnak().item_value()
                for statement in self.entity(entity_ref).truthy_statements(
                    wikidata_value.P_INSTANCE_OF
                )
            )
        return self._entity_classes[entity_ref]

    def forms_of_creative_work(
        self, item_ref: wikidata_value.ItemRef
    ) -> Set[wikidata_value.ItemRef]:
        """Returns the forms of the creative work."""
        if item_ref not in self._forms_of_creative_work:
            self._forms_of_creative_work[item_ref] = frozenset(
                statement.mainsnak().item_value()
                for statement in self.entity(item_ref).truthy_statements(
                    wikidata_value.P_FORM_OF_CREATIVE_WORK
                )
            )
        return self._forms_of_creative_work[item_ref]

    def transitive_subclasses(
        self, class_ref: wikidata_value.ItemRef
    ) -> Set[wikidata_value.ItemRef]:
        """Returns transitive subclasses of the given class."""
        if class_ref not in self._transitive_subclasses:
            subclass_of = wikidata_value.P_SUBCLASS_OF.id
            results = self.sparql(
                "SELECT REDUCED ?class WHERE { "
                f"?class (wdt:{subclass_of}|owl:sameAs)* wd:{class_ref.id}. "
                "?class wikibase:sitelinks []. "
                "}"
            )
            self._transitive_subclasses[class_ref] = frozenset(
                wikidata_value.parse_sparql_term_item(result["class"])
                for result in results
            )
        return self._transitive_subclasses[class_ref]

    def related_media(self, item_ref: wikidata_value.ItemRef) -> RelatedMedia:
        """Returns related media."""
        # This also gets the classes for the related items and stores them for
        # later use by entity_classes(), to save many API calls for related
        # media that aren't going to be looked at any further than checking
        # their classes.
        if item_ref not in self._related_media:
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
            form = wikidata_value.P_FORM_OF_CREATIVE_WORK.id
            query = " ".join(
                (
                    "SELECT REDUCED ?item ?relation ?class ?form WHERE {",
                    " UNION ".join(
                        (
                            "{ "
                            f"wd:{item_ref.id} "
                            f"^owl:sameAs?/({predicate})/owl:sameAs? ?item. "
                            f'BIND ("{relation}" AS ?relation) '
                            "}"
                        )
                        for relation, predicate in predicate_by_relation.items()
                    ),
                    "FILTER (!wikibase:isSomeValue(?item))",
                    "FILTER NOT EXISTS { ?item owl:sameAs ?other }",
                    f"OPTIONAL {{ ?item wdt:{instance_of} ?class. }}",
                    f"OPTIONAL {{ ?item wdt:{form} ?form. }}",
                    "}",
                )
            )
            results = self.sparql(query)
            item_classes: collections.defaultdict[
                wikidata_value.ItemRef, set[wikidata_value.ItemRef]
            ] = collections.defaultdict(set)
            item_forms: collections.defaultdict[
                wikidata_value.ItemRef, set[wikidata_value.ItemRef]
            ] = collections.defaultdict(set)
            items_by_relation: collections.defaultdict[
                str, set[wikidata_value.ItemRef]
            ] = collections.defaultdict(set)
            for result in results:
                related_item = wikidata_value.parse_sparql_term_item(
                    result["item"]
                )
                related_item_classes = item_classes[related_item]
                if "class" in result:
                    related_item_classes.add(
                        wikidata_value.parse_sparql_term_item(result["class"])
                    )
                related_item_forms = item_forms[related_item]
                if "form" in result:
                    related_item_forms.add(
                        wikidata_value.parse_sparql_term_item(result["form"])
                    )
                items_by_relation[
                    wikidata_value.parse_sparql_term_string(result["relation"])
                ].add(related_item)
            for related_item, classes in item_classes.items():
                self._entity_classes.setdefault(
                    related_item, frozenset(classes)
                )
            for related_item, forms in item_forms.items():
                self._forms_of_creative_work.setdefault(
                    related_item, frozenset(forms)
                )
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
            self._related_media[item_ref] = related_media
        return self._related_media[item_ref]


def _is_positive_integer(value: str) -> bool:
    try:
        int_value = int(value)
    except ValueError:
        return False
    return int_value > 0


def _replace_pseudo_datetimes(
    values: Iterable[datetime.datetime | wikidata_value.PseudoDatetime | None],
) -> Iterable[datetime.datetime | None]:
    """Yields values with pseudo datetimes replaced by placeholders."""
    for value in values:
        match value:
            case datetime.datetime() | None:
                yield value
            case wikidata_value.PseudoDatetime.PAST:
                yield datetime.datetime(
                    1, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
                )
            case _:
                typing.assert_never(value)


def _release_status(
    item: wikidata_value.Entity,
    *,
    now: datetime.datetime,
) -> config_pb2.WikidataFilter.ReleaseStatus.ValueType:
    start = _min(
        (
            _min(_replace_pseudo_datetimes(statement.time_value()))
            for statement in item.truthy_statements(wikidata_value.P_START_TIME)
        )
    )
    end = _max(
        (
            _max(_replace_pseudo_datetimes(statement.time_value()))
            for statement in item.truthy_statements(wikidata_value.P_END_TIME)
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
                _min(_replace_pseudo_datetimes(statement.time_value()))
                for statement in item.truthy_statements(prop)
            )
        )
        if released is None:
            continue
        elif released <= now:
            return config_pb2.WikidataFilter.ReleaseStatus.RELEASED
        else:
            return config_pb2.WikidataFilter.ReleaseStatus.UNRELEASED
    return config_pb2.WikidataFilter.ReleaseStatus.RELEASE_STATUS_UNSPECIFIED


def _pop_unprocessed(
    unprocessed: dict[_RelatedMediaPriority, set[wikidata_value.ItemRef]],
) -> wikidata_value.ItemRef:
    for priority in sorted(_RelatedMediaPriority, reverse=True):
        if unprocessed[priority]:
            return unprocessed[priority].pop()
    raise KeyError("pop from empty unprocessed")


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

        self._config_ignore = tuple(
            map(
                wikidata_value.ItemRef.from_string,
                self._config.related_media.ignore,
            )
        )
        self._config_classes_ignore = tuple(
            map(
                wikidata_value.ItemRef.from_string,
                self._config.related_media.classes_ignore,
            )
        )
        self._config_classes_ignore_excluded = tuple(
            map(
                wikidata_value.ItemRef.from_string,
                self._config.related_media.classes_ignore_excluded,
            )
        )

    @functools.cached_property
    def _fictional_entity_classes(self) -> Set[wikidata_value.ItemRef]:
        # Fictional entities (other than fictional universes) can be part of
        # fictional universes, but they're not media items.
        return {
            *self._api.transitive_subclasses(
                wikidata_value.Q_CLASS_OF_FICTIONAL_ENTITIES
            ),
            *(
                self._api.transitive_subclasses(
                    wikidata_value.Q_FICTIONAL_ENTITY
                )
                - self._api.transitive_subclasses(
                    wikidata_value.Q_FICTIONAL_UNIVERSE
                )
            ),
        }

    @functools.cached_property
    def _ignored_items(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._config_ignore,
            # Sometimes these classes are linked to media, instead of instances
            # of those classes being linked to the media.
            *self._fictional_entity_classes,
            wikidata_value.Q_OMNIVERSE,
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
    def _ignored_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *(
                frozenset(
                    itertools.chain.from_iterable(
                        map(
                            self._api.transitive_subclasses,
                            self._config_classes_ignore,
                        )
                    )
                )
                - frozenset(
                    itertools.chain.from_iterable(
                        map(
                            self._api.transitive_subclasses,
                            self._config_classes_ignore_excluded,
                        )
                    )
                )
            ),
            *self._api.transitive_subclasses(wikidata_value.Q_BOX_OFFICE),
            *self._fictional_entity_classes,
            *self._api.transitive_subclasses(wikidata_value.Q_LIST),
            # "to be announced" <https://www.wikidata.org/wiki/Q603908> is
            # sometimes used for "followed by" statements, but it's not a useful
            # thing to list, and it's connected to many unrelated things.
            *self._api.transitive_subclasses(wikidata_value.Q_PLACEHOLDER_NAME),
            # Disambiguation pages and the like are not media items.
            *self._api.transitive_subclasses(
                wikidata_value.Q_WIKIMEDIA_PAGE_OUTSIDE_THE_MAIN_KNOWLEDGE_TREE
            ),
        }

    def _ignored_classes_from_request(
        self,
        request: media_filter.FilterRequest,
    ) -> Set[wikidata_value.ItemRef]:
        return frozenset(
            itertools.chain.from_iterable(
                map(
                    self._api.transitive_subclasses,
                    request.item.wikidata_classes_ignore_recursive,
                )
            )
        ) - frozenset(
            itertools.chain.from_iterable(
                map(
                    self._api.transitive_subclasses,
                    request.item.wikidata_classes_ignore_excluded_recursive,
                )
            )
        )

    @functools.cached_property
    def _anthology_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_ANTHOLOGY),
            *self._api.transitive_subclasses(wikidata_value.Q_ANTHOLOGY_FILM),
        }

    @functools.cached_property
    def _composite_episode_classes(self) -> Set[wikidata_value.ItemRef]:
        """Classes for multi-part episodes of unspecified parent type."""
        return self._api.transitive_subclasses(
            wikidata_value.Q_COMPOSITE_EPISODE
        )

    @functools.cached_property
    def _music_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_MUSICAL_WORK),
            *self._api.transitive_subclasses(wikidata_value.Q_RELEASE_GROUP),
        }

    @functools.cached_property
    def _tv_show_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_SERIES
        )

    @functools.cached_property
    def _tv_season_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_SERIES_SEASON
        )

    @functools.cached_property
    def _tv_season_part_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_PART_OF_TELEVISION_SEASON
        )

    @functools.cached_property
    def _tv_season_part_parent_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._tv_show_classes,
            *self._tv_season_classes,
        }

    @functools.cached_property
    def _tv_episode_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._composite_episode_classes,
            *self._api.transitive_subclasses(
                wikidata_value.Q_TELEVISION_SERIES_EPISODE
            ),
        }

    @functools.cached_property
    def _tv_episode_parent_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._tv_season_part_parent_classes,
            *self._tv_season_part_classes,
            *self._composite_episode_classes,
        }

    @functools.cached_property
    def _tv_episode_segment_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_SEGMENT_OF_A_TELEVISION_EPISODE
        )

    @functools.cached_property
    def _tv_episode_segment_parent_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._tv_episode_parent_classes,
            *self._tv_episode_classes,
        }

    @functools.cached_property
    def _tv_pilot_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(
            wikidata_value.Q_TELEVISION_PILOT
        )

    @functools.cached_property
    def _possible_tv_special_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_TELEVISION_FILM),
            *self._api.transitive_subclasses(
                wikidata_value.Q_TELEVISION_SPECIAL
            ),
        }

    @functools.cached_property
    def _web_series_classes(self) -> Set[wikidata_value.ItemRef]:
        return self._api.transitive_subclasses(wikidata_value.Q_WEB_SERIES)

    @functools.cached_property
    def _web_series_child_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(
                wikidata_value.Q_WEB_SERIES_SEASON
            ),
            *self._composite_episode_classes,
            *self._api.transitive_subclasses(
                wikidata_value.Q_WEB_SERIES_EPISODE
            ),
            *self._api.transitive_subclasses(
                wikidata_value.Q_TELEVISION_SERIES_EPISODE
            ),
            *self._api.transitive_subclasses(wikidata_value.Q_FILM),
        }

    @functools.cached_property
    def _video_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_FILM),
            *self._tv_episode_classes,
            *self._tv_pilot_classes,
            *self._possible_tv_special_classes,
        }

    @functools.cached_property
    def _video_part_classes(self) -> Set[wikidata_value.ItemRef]:
        return {
            *self._api.transitive_subclasses(wikidata_value.Q_SCENE),
        }

    @functools.cached_property
    def _priority_by_classes(
        self,
    ) -> Sequence[tuple[_RelatedMediaPriority, Set[wikidata_value.ItemRef]]]:
        """Returns priorities and classes that should be assigned to them."""
        return (
            (
                _RelatedMediaPriority.UNLIKELY,
                {
                    *self._api.transitive_subclasses(wikidata_value.Q_CHAPTER),
                    *self._tv_season_classes,
                    *self._tv_season_part_classes,
                    *self._tv_episode_classes,
                    *self._tv_episode_segment_classes,
                    *self._video_part_classes,
                    *self._api.transitive_subclasses(
                        wikidata_value.Q_WEB_SERIES_SEASON
                    ),
                    *self._api.transitive_subclasses(
                        wikidata_value.Q_WEB_SERIES_EPISODE
                    ),
                },
            ),
            (
                _RelatedMediaPriority.POSSIBLE,
                {
                    *self._api.transitive_subclasses(wikidata_value.Q_NOVELLA),
                    *self._api.transitive_subclasses(
                        wikidata_value.Q_SHORT_STORY
                    ),
                },
            ),
        )

    def _is_ignored(
        self,
        item_ref: wikidata_value.ItemRef,
        *,
        request: media_filter.FilterRequest,
        ignored_from_config: set[wikidata_value.ItemRef],
        ignored_classes_from_request: Set[wikidata_value.ItemRef],
    ) -> bool:
        if item_ref in request.item.wikidata_ignore_items_recursive:
            ignored_from_config.add(item_ref)
            return True
        elif item_ref in self._ignored_items:
            return True
        item_classes = self._api.entity_classes(item_ref)
        return bool(
            item_classes & self._ignored_classes
            or item_classes & ignored_classes_from_request
        )

    def _should_cross_parent_child_border(
        self, parent: wikidata_value.ItemRef, child: wikidata_value.ItemRef
    ) -> bool:
        """Returns whether to cross the parent-child border for related media.

        Some parent-child pairs cross the border between generally unrelated
        sets of media. E.g., somebody interested in watching a series of
        anthology films might want to know all the films in the series. But
        there could be many items related to stories in the individual
        anthologies, and those items don't have much of a connection to the
        series of anthologies that the user is interested in. Or from the other
        side, if the user is interested in a book that was adapted into a part
        of an anthology movie, they might be interested in that part of the
        anthology movie, but not necessarily in the entire anthology series.

        Args:
            parent: Parent.
            child: Child.
        """
        del child  # Unused.
        parent_classes = self._api.entity_classes(parent)
        parent_forms = self._api.forms_of_creative_work(parent)
        return (
            not parent_classes & self._anthology_classes
            and not parent_forms & self._anthology_classes
        )

    def _integral_child_classes(
        self,
    ) -> Iterable[
        tuple[Set[wikidata_value.ItemRef], Set[wikidata_value.ItemRef]]
    ]:
        """Yields (parent, child) classes that indicate an integral child."""
        yield (
            self._api.transitive_subclasses(wikidata_value.Q_LITERARY_WORK),
            self._api.transitive_subclasses(wikidata_value.Q_CHAPTER),
        )
        yield (self._tv_show_classes, self._tv_season_classes)
        yield (
            self._tv_season_part_parent_classes,
            self._tv_season_part_classes,
        )
        yield (
            self._tv_episode_segment_parent_classes,
            self._tv_episode_segment_classes,
        )
        yield (self._web_series_classes, self._web_series_child_classes)
        yield (self._video_classes, self._video_classes)
        yield (self._video_classes, self._video_part_classes)
        yield (self._video_classes, self._music_classes)
        yield (self._tv_show_classes, self._music_classes)
        yield (self._tv_season_classes, self._music_classes)
        yield (self._tv_season_part_classes, self._music_classes)
        yield (self._music_classes, self._music_classes)

    def _is_integral_child(
        self, parent: wikidata_value.ItemRef, child: wikidata_value.ItemRef
    ) -> bool:
        """Returns whether child is an integral child of parent.

        An integral child (as defined here) is an item that a casual
        viewer/reader/etc. of the parent would likely view/read/etc. with no
        additional effort. E.g., somebody who casually watched a TV show and
        thought they had finished that show probably watched all the regular
        seasons and episodes of that show. But they could have missed the
        specials. So the regular seasons and episodes are considered integral
        children of the show (because it's unnecessary noise to list all of
        them), but the specials are not (because listing them could help the
        user find something they missed).

        Args:
            parent: Parent.
            child: Child.
        """
        if not self._should_cross_parent_child_border(parent, child):
            return False
        parent_classes = self._api.entity_classes(parent)
        parent_classes_and_forms = (
            parent_classes | self._api.forms_of_creative_work(parent)
        )
        child_classes = self._api.entity_classes(child)
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
            child_classes & self._tv_pilot_classes
            and parent_classes & self._tv_episode_parent_classes
        ):
            # Some pilots are regular episodes, some aren't. This code assumes
            # that if all of the pilot's ordinals (e.g., episode number and
            # season number) are positive integers (like in the common case of
            # S1E1), it's a regular episode.
            pilot = self._api.entity(child)
            has_ordinals = False
            for statement in (
                *pilot.truthy_statements(wikidata_value.P_SEASON),
                *pilot.truthy_statements(wikidata_value.P_PART_OF_THE_SERIES),
            ):
                for snak in statement.qualifiers(
                    wikidata_value.P_SERIES_ORDINAL
                ):
                    has_ordinals = True
                    if not _is_positive_integer(snak.string_value()):
                        return False
            return has_ordinals
        if (
            child_classes & self._tv_episode_classes
            and not child_classes & self._possible_tv_special_classes
            and parent_classes & self._tv_episode_parent_classes
        ):
            return True
        if (
            parent_classes_and_forms
            & self._api.transitive_subclasses(
                wikidata_value.Q_COLLECTION_OF_LITERARY_WORKS
            )
        ) and (
            child_classes
            & self._api.transitive_subclasses(wikidata_value.Q_LITERARY_WORK)
        ):
            return True
        return False

    def _integral_children(
        self, item_ref: wikidata_value.ItemRef, related: RelatedMedia
    ) -> Iterable[wikidata_value.ItemRef]:
        if any(
            self._is_integral_child(parent, item_ref)
            for parent in related.parents
        ):
            yield item_ref
        yield from (
            child
            for child in related.children
            if self._is_integral_child(item_ref, child)
        )

    def _related_item_priority(
        self, item_ref: wikidata_value.ItemRef
    ) -> _RelatedMediaPriority:
        item_classes_and_forms = self._api.entity_classes(
            item_ref
        ) | self._api.forms_of_creative_work(item_ref)
        for priority, priority_classes in self._priority_by_classes:
            if item_classes_and_forms & priority_classes:
                return priority
        return _RelatedMediaPriority.LIKELY

    def _update_unprocessed(
        self,
        iterable: Iterable[wikidata_value.ItemRef],
        /,
        *,
        current: wikidata_value.ItemRef,
        reached_from: dict[wikidata_value.ItemRef, wikidata_value.ItemRef],
        unprocessed: dict[_RelatedMediaPriority, set[wikidata_value.ItemRef]],
    ) -> None:
        for item_ref in iterable:
            if item_ref not in reached_from:
                logging.debug("%s reached from %s", item_ref, current)
                reached_from[item_ref] = current
            unprocessed[self._related_item_priority(item_ref)].add(item_ref)

    def _related_item_result_extra(
        self,
        category: str,
        item_ref: wikidata_value.ItemRef,
    ) -> media_filter.ResultExtra:
        entity = self._api.entity(item_ref)
        item_description_parts = []
        if (label := entity.label(self._config.languages)) is not None:
            item_description_parts.append(label)
        if (
            description := entity.description(self._config.languages)
        ) is not None:
            item_description_parts.append(f"({description})")
        item_description_parts.append(f"<{item_ref}>")
        return media_filter.ResultExtra(
            human_readable=f"{category}: {' '.join(item_description_parts)}",
        )

    def _related_media(
        self, request: media_filter.FilterRequest
    ) -> Set[media_filter.ResultExtra]:
        if request.item.has_parent:
            return frozenset()
        items_from_config = request.item.all_wikidata_items_recursive
        assert request.item.wikidata_item is not None  # Already checked.
        reached_from: dict[wikidata_value.ItemRef, wikidata_value.ItemRef] = {}
        ignored_from_config: set[wikidata_value.ItemRef] = set()
        unprocessed: dict[
            _RelatedMediaPriority, set[wikidata_value.ItemRef]
        ] = {
            _RelatedMediaPriority.UNLIKELY: set(),
            _RelatedMediaPriority.POSSIBLE: set(),
            _RelatedMediaPriority.LIKELY: {request.item.wikidata_item},
        }
        processed: set[wikidata_value.ItemRef] = set()
        loose: set[wikidata_value.ItemRef] = set()
        integral_children: set[wikidata_value.ItemRef] = set()
        is_ignored = functools.partial(
            self._is_ignored,
            request=request,
            ignored_from_config=ignored_from_config,
            ignored_classes_from_request=self._ignored_classes_from_request(
                request
            ),
        )
        while any(unprocessed.values()):
            if (
                sum(
                    len(items)
                    for priority, items in unprocessed.items()
                    if priority > _RelatedMediaPriority.UNLIKELY
                )
                + len(processed)
                > 1000
            ):
                raise ValueError(
                    "Too many related media items reached from "
                    f"{request.item.wikidata_item}:\n"
                    + "\n".join(
                        f"  {key} reached from {value}"
                        for key, value in reached_from.items()
                    )
                )
            current = _pop_unprocessed(unprocessed)
            processed.add(current)
            related = self._api.related_media(current)
            integral_children.update(self._integral_children(current, related))
            update_unprocessed = functools.partial(
                self._update_unprocessed,
                current=current,
                reached_from=reached_from,
                unprocessed=unprocessed,
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
            for unprocessed_set in unprocessed.values():
                unprocessed_set -= integral_children
        return {
            *(
                self._related_item_result_extra("related item", item)
                for item in processed - items_from_config - integral_children
            ),
            *(
                self._related_item_result_extra("loosely-related item", item)
                for item in (
                    loose - processed - items_from_config - integral_children
                )
            ),
            *(
                media_filter.ResultExtra(
                    human_readable=(
                        "item in config file that's not related to "
                        f"{request.item.wikidata_item}: {item}"
                    ),
                )
                for item in items_from_config - processed - loose
            ),
            *(
                media_filter.ResultExtra(
                    human_readable=(
                        f"item configured to be ignored, but not found: {item}"
                    ),
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
                item = self._api.entity(request.item.wikidata_item)
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
