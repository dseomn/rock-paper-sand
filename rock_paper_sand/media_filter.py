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
from collections.abc import Callable, Iterable, Set
import dataclasses
import itertools
import re
from typing import Any

import immutabledict

from rock_paper_sand import media_item
from rock_paper_sand import multi_level_set
from rock_paper_sand.proto import config_pb2


class ResultExtra(immutabledict.immutabledict[str, Any]):
    """Extra information about a filter result.

    Keys should generally be scoped with dots. E.g., the justwatch filter should
    use keys like "justwatch.provider" instead of just "provider".
    """

    def human_readable(self) -> str | None:
        """Returns a human-readable description of the extra info, or None."""
        return None


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
    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """Returns the result of the filter on the media item."""
        raise NotImplementedError()


class CachedFilter(Filter, abc.ABC):
    """Base class for filters that cache their results.

    Child classes should override filter_implementation() instead of filter().
    """

    def __init__(self) -> None:
        self._result_by_id: dict[str, FilterResult] = {}

    @abc.abstractmethod
    def filter_implementation(self, item: media_item.MediaItem) -> FilterResult:
        """See Filter.filter."""
        raise NotImplementedError()

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        if item.id not in self._result_by_id:
            self._result_by_id[item.id] = self.filter_implementation(item)
        return self._result_by_id[item.id]


class Not(Filter):
    """Inverts another filter."""

    def __init__(self, child: Filter, /) -> None:
        self._child = child

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return self._child.valid_extra_keys()

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        child_result = self._child.filter(item)
        return FilterResult(not child_result.matches, extra=child_result.extra)


class BinaryLogic(Filter):
    """Binary logic filter, i.e., "and" and "or"."""

    def __init__(
        self, *children: Filter, op: Callable[[Iterable[bool]], bool]
    ) -> None:
        self._children = children
        self._op = op

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return frozenset(
            itertools.chain.from_iterable(
                child.valid_extra_keys() for child in self._children
            )
        )

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        results = tuple(child.filter(item) for child in self._children)
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

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        return FilterResult(bool(item.parts) == self._has_parts)


class Done(Filter):
    """Matches based on the `done` field."""

    def __init__(self, done: str) -> None:
        self._done = multi_level_set.parse_number(done)

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        return FilterResult(self._done in item.done)


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

    def filter(self, item: media_item.MediaItem) -> FilterResult:
        """See base class."""
        return FilterResult(self._matcher(self._field_getter(item.proto)))


class Registry:
    """Registry of filters."""

    def __init__(
        self,
        *,
        justwatch_factory: (
            Callable[[config_pb2.JustWatchFilter], Filter] | None
        ) = None,
    ) -> None:
        """Initializer.

        Args:
            justwatch_factory: Callback to create a JustWatch filter, or None to
                raise an error if there are any JustWatch filters.
        """
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
            case "custom_availability":
                return StringFieldMatcher(
                    lambda item: item.custom_availability,
                    filter_config.custom_availability,
                )
            case "justwatch":
                if self._justwatch_factory is None:
                    raise ValueError(
                        "A JustWatch filter was specified, but no callback to "
                        "handle those was provided."
                    )
                return self._justwatch_factory(filter_config.justwatch)
            case _:
                raise ValueError(f"Unknown filter type: {filter_config!r}")
