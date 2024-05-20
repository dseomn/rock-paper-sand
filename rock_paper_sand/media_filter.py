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
"""Filters for media items."""

import abc
from collections.abc import Callable, Hashable, Mapping, Set
import dataclasses
import datetime
import functools
import itertools
import re
from typing import Any, Self

import immutabledict
import jmespath
import jmespath.parser

from rock_paper_sand import exceptions
from rock_paper_sand import media_item
from rock_paper_sand import multi_level_set
from rock_paper_sand.proto import config_pb2


@dataclasses.dataclass(frozen=True)
class FilterRequest:
    """Arguments to a filter.

    This uses a dataclass to store the arguments instead of passing multiple
    (keyword) arguments so that new arguments can be added without changing the
    signature of existing filters.

    Attributes:
        item: Item to filter.
        now: Time to use as the current time for filtering. E.g., if a filter
            checks if the item is currently available for streaming, it should
            use this time to compare against the range of times that the item is
            available.
        result_ignored_if_matches_is: Used to short-circuit logical combinations
            without affecting results. If bool, a matching FilterResult.matches
            value will cause the result to be ignored. If None, the result is
            never ignored.
    """

    item: media_item.MediaItem
    _: dataclasses.KW_ONLY
    now: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    result_ignored_if_matches_is: bool | None = None

    def cache_key(self) -> Hashable:
        """Returns a key that identifies this request for caching.

        WARNING: This does not include result_ignored_if_matches_is, so cached
        filters should not use that field.
        """
        return (self.item.id, self.now)

    def replace_result_ignored_if_matches_is(new: bool | None, /) -> Self:
        """Returns a copy with a new result_ignored_if_matches_is value."""
        return dataclases.replace(self, result_ignored_if_matches_is=new)


@dataclasses.dataclass(frozen=True, kw_only=True)
class ResultExtra:
    """Extra information about a filter result.

    Attributes:
        human_readable: Human-readable description of the extra info, or None.
        data: Data for grouping or use by parent filters. Keys should generally
            be scoped with dots. E.g., the justwatch filter should use keys like
            "justwatch.provider" instead of just "provider".
    """

    human_readable: str | None = None
    data: Mapping[str, Any] = immutabledict.immutabledict()


@dataclasses.dataclass(frozen=True)
class FilterResult:
    """Result from running a filter on an item of media.

    Attributes:
        matches: Whether the media matches the filter.
        extra: Any extra information provided by the filter.
    """

    matches: bool
    _: dataclasses.KW_ONLY
    extra: Set[ResultExtra] = frozenset()


class Filter(abc.ABC):
    """Base class for filtering media and optionally adding additional info."""

    def valid_extra_keys(self) -> Set[str]:
        """Returns valid keys that could be used in FilterResult.extra."""
        return frozenset()

    @abc.abstractmethod
    def filter(self, request: FilterRequest) -> FilterResult:
        """Returns the result of the filter on the media item."""
        raise NotImplementedError()


class CachedFilter(Filter, abc.ABC):
    """Base class for filters that cache their results.

    Child classes should override filter_implementation() instead of filter().
    """

    def __init__(self) -> None:
        self._results: dict[Hashable, FilterResult] = {}

    @abc.abstractmethod
    def filter_implementation(self, request: FilterRequest) -> FilterResult:
        """See Filter.filter."""
        raise NotImplementedError()

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        cache_key = request.cache_key()
        if cache_key not in self._results:
            self._results[cache_key] = self.filter_implementation(request)
        return self._results[cache_key]


class Not(Filter):
    """Inverts another filter."""

    def __init__(self, child: Filter, /) -> None:
        self._child = child

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return self._child.valid_extra_keys()

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        child_result = self._child.filter(
            request.replace_result_ignored_if_matches_is(
                None
                if request.result_ignored_if_matches_is is None
                else not request.result_ignored_if_matches_is
            )
        )
        return FilterResult(not child_result.matches, extra=child_result.extra)


class BinaryLogic(Filter, abc.ABC):
    """Binary logic filter, i.e., "and" and "or".

    Attributes:
        children: Child filters.
    """

    def __init__(self, *children: Filter) -> None:
        self.children = children

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return frozenset(
            itertools.chain.from_iterable(
                child.valid_extra_keys() for child in self.children
            )
        )

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        matches = self._default
        extra = set()
        if self._short_circuit_on == request.result_ignored_if_matches_is:
            result_ignored_if_matches_is = request.result_ignored_if_matches_is
        else:
            result_ignored_if_matches_is = None
        for child_num, child in enumerate(self._children):
            if (
                matches
                == self._short_circuit_on
                == request.result_ignored_if_matches_is
            ):
                break
            if child_num == len(self._children) - 1:
                child_request = request.replace_result_ignored_if_matches_is(
                    None
                    if request.result_ignored_if_matches_is is None
                    else not request.result_ignored_if_matches_is
                )
            result = child.filter(request)
            matches = self._op(matches, result.matches)
            extra.update(result.extra)
        return FilterResult(
            self._op(result.matches for result in results),
            extra=frozenset(
                itertools.chain.from_iterable(
                    result.extra for result in results
                )
            ),
        )


class And(BinaryLogic):
    """Intersects other filters."""

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        matches = True
        extra = set()
        for child_num, child in enumerate(self.children):
            match request.result_ignored_if_matches_is:
                case None:
                    child_result_ignored_if_matches_is = None
                case True if not matches:
                    # The final result will be False regardless of the child,
                    # and a False result is not ignored, so the child's result
                    # is never ignored.
                    child_result_ignored_if_matches_is = None
                case True if child_num == len(self.children) - 1:
                    # The final result will be the same as this (last) child's
                    # result, so the ignored value is the same.
                    child_result_ignored_if_matches_is = True
                case True:
                    # The child can't ignore True, because a subsequent child
                    # might return False, which would make the final result
                    # False which is not ignored.
                    child_result_ignored_if_matches_is = None
                case False:
                    child_result_ignored_if_matches_is = False
            result = child.filter(
                request.replace_result_ignored_if_matches_is(
                    child_result_ignored_if_matches_is
                )
            )
            if not result.matches:
                matches = False
                if request.result_ignored_if_matches_is == False:
                    break
            extra.update(result.extra)
        return FilterResult(
            self._op(result.matches for result in results),
            extra=frozenset(
                itertools.chain.from_iterable(
                    result.extra for result in results
                )
            ),
        )


class HasParts(Filter):
    """Matches based on whether there are any child parts."""

    def __init__(self, has_parts: bool) -> None:
        self._has_parts = has_parts

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        return FilterResult(bool(request.item.parts) == self._has_parts)


class Done(Filter):
    """Matches based on the `done` field."""

    def __init__(self, done: str) -> None:
        self._done = multi_level_set.parse_number(done)

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        return FilterResult(self._done in request.item.done)


class StringFieldMatcher(Filter):
    """Matches a string field."""

    def __init__(
        self,
        field_getter: Callable[[config_pb2.MediaItem], str],
        matcher_config: config_pb2.StringFieldMatcher,
    ) -> None:
        self._field_getter = field_getter
        match matcher_config.WhichOneof("method"):
            case "empty":
                self._matcher = (
                    lambda value: bool(value) != matcher_config.empty
                )
            case "equals":
                self._matcher = lambda value: value == matcher_config.equals
            case "regex":
                compiled = re.compile(matcher_config.regex)
                self._matcher = lambda value: compiled.search(value) is not None
            case _:
                raise ValueError(
                    f"Unknown string field match type: {matcher_config!r}"
                )

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        return FilterResult(
            self._matcher(self._field_getter(request.item.proto))
        )


def _jmespath_matcher(
    expression: jmespath.parser.ParsedResult,
    data: Any,
) -> bool:
    match expression.search(data):
        case False | None:
            return False
        case True:
            return True
        case return_value:
            raise ValueError(
                f"JMESPath expression returned invalid value {return_value!r} "
                f"for data {data!r}"
            )


class ArbitraryDataMatcher(Filter):
    """Matches arbitrary JSON data."""

    def __init__(
        self,
        field_getter: Callable[[media_item.MediaItem], Any],
        matcher_config: config_pb2.ArbitraryDataMatcher,
    ) -> None:
        self._field_getter = field_getter
        self._config = matcher_config
        match matcher_config.WhichOneof("method"):
            case "jmespath":
                self._matcher = functools.partial(
                    _jmespath_matcher, jmespath.compile(matcher_config.jmespath)
                )
            case _:
                raise ValueError(
                    f"Unknown arbitrary data match type: {matcher_config!r}"
                )

    def filter(self, request: FilterRequest) -> FilterResult:
        """See base class."""
        data = self._field_getter(request.item)
        if data is None:
            return FilterResult(False)
        with exceptions.add_note(
            f"While filtering {request.item.debug_description} using "
            f"ArbitraryDataMatcher filter config:\n{self._config}"
        ):
            return FilterResult(self._matcher(data))


class Registry:
    """Registry of filters."""

    def __init__(
        self,
        *,
        wikidata_factory: (
            Callable[[config_pb2.WikidataFilter], Filter] | None
        ) = None,
        justwatch_factory: (
            Callable[[config_pb2.JustWatchFilter], Filter] | None
        ) = None,
    ) -> None:
        """Initializer.

        Args:
            wikidata_factory: Callback to create a Wikidata filter, or None to
                raise an error if there are any Wikidata filters.
            justwatch_factory: Callback to create a JustWatch filter, or None to
                raise an error if there are any JustWatch filters.
        """
        self._wikidata_factory = wikidata_factory
        self._justwatch_factory = justwatch_factory
        self._filter_by_name: dict[str, Filter] = {}

    def register(self, name: str, filter_: Filter) -> None:
        """Registers a named filter."""
        if name in self._filter_by_name:
            raise ValueError(f"Filter {name!r} is defined multiple times.")
        self._filter_by_name[name] = filter_

    def parse(self, filter_config: config_pb2.Filter) -> Filter:
        """Returns a Filter instance from its configuration."""
        match filter_config.WhichOneof("filter"):
            case "all":
                return BinaryLogic(op=all)
            case "ref":
                return self._filter_by_name[filter_config.ref]
            case "not":
                return Not(self.parse(getattr(filter_config, "not")))
            case "and":
                return BinaryLogic(
                    *map(self.parse, getattr(filter_config, "and").filters),
                    op=all,
                )
            case "or":
                return BinaryLogic(
                    *map(self.parse, getattr(filter_config, "or").filters),
                    op=any,
                )
            case "has_parts":
                return HasParts(filter_config.has_parts)
            case "done":
                return Done(filter_config.done)
            case "name":
                return StringFieldMatcher(
                    lambda item: item.name, filter_config.name
                )
            case "custom_data":
                return ArbitraryDataMatcher(
                    lambda item: item.custom_data, filter_config.custom_data
                )
            case "custom_availability":
                return StringFieldMatcher(
                    lambda item: item.custom_availability,
                    filter_config.custom_availability,
                )
            case "wikidata":
                if self._wikidata_factory is None:
                    raise ValueError(
                        "A Wikidata filter was specified, but no callback to "
                        "handle those was provided."
                    )
                return self._wikidata_factory(filter_config.wikidata)
            case "justwatch":
                if self._justwatch_factory is None:
                    raise ValueError(
                        "A JustWatch filter was specified, but no callback to "
                        "handle those was provided."
                    )
                return self._justwatch_factory(filter_config.justwatch)
            case _:
                raise ValueError(f"Unknown filter type: {filter_config!r}")
