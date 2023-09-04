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
from collections.abc import Callable, Mapping, Set
import dataclasses
import functools

from rock_paper_sand import config_pb2


@dataclasses.dataclass(frozen=True)
class FilterResult:
    """Result from running a filter on an item of media.

    Attributes:
        matches: Whether the media matches the filter.
        extra: Any extra information provided by the filter, e.g., what
            streaming services the media is available on.
    """

    matches: bool
    _: dataclasses.KW_ONLY
    extra: Set[str] = frozenset()


class Filter(abc.ABC):
    """Base class for filtering media and optionally adding additional info."""

    @abc.abstractmethod
    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """Returns the result of the filter on the media item."""
        raise NotImplementedError()


class Not(Filter):
    """Inverts another filter."""

    def __init__(self, child: Filter, /):
        self._child = child

    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """See base class."""
        child_result = self._child.filter(media_item)
        return FilterResult(not child_result.matches, extra=child_result.extra)


class And(Filter):
    """Intersects other filters."""

    def __init__(self, *children: Filter):
        self._children = children

    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """See base class."""
        extra = set()
        for child in self._children:
            child_result = child.filter(media_item)
            extra.update(child_result.extra)
            if not child_result.matches:
                return FilterResult(False, extra=extra)
        return FilterResult(True, extra=extra)


class Or(Filter):
    """Unions other filters."""

    def __init__(self, *children: Filter):
        self._children = children

    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """See base class."""
        extra = set()
        for child in self._children:
            child_result = child.filter(media_item)
            extra.update(child_result.extra)
            if child_result.matches:
                return FilterResult(True, extra=extra)
        return FilterResult(False, extra=extra)


class HasParts(Filter):
    """Matches based on whether there are any child parts."""

    def __init__(self, has_parts: bool):
        self._has_parts = has_parts

    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """See base class."""
        return FilterResult(bool(media_item.parts) == self._has_parts)


class StringFieldMatcher(Filter):
    """Matches a string field."""

    def __init__(
        self,
        field_getter: Callable[[config_pb2.MediaItem], str],
        matcher_config: config_pb2.StringFieldMatcher,
    ):
        self._field_getter = field_getter
        self._matcher_config = matcher_config

    def filter(self, media_item: config_pb2.MediaItem) -> FilterResult:
        """See base class."""
        value = self._field_getter(media_item)
        match self._matcher_config.WhichOneof("method"):
            case "empty":
                return FilterResult(bool(value) != self._matcher_config.empty)
            case "equals":
                return FilterResult(value == self._matcher_config.equals)
            case _:
                raise ValueError(
                    f"Unknown string field match type: {self._matcher_config!r}"
                )


class Registry:
    """Registry of filters."""

    def __init__(
        self,
        *,
        justwatch_factory: (
            Callable[[config_pb2.JustWatchFilter], Filter] | None
        ) = None,
    ):
        """Initializer.

        Args:
            justwatch_factory: Callback to create a JustWatch filter, or None to
                raise an error if there are any JustWatch filters.
        """
        self._justwatch_factory = justwatch_factory
        self._filter_by_name = {}

    def register(self, name: str, filter_: Filter):
        """Registers a named filter."""
        if name in self._filter_by_name:
            raise ValueError(f"Filter {name!r} is defined multiple times.")
        self._filter_by_name[name] = filter_

    def parse(self, filter_config: config_pb2.Filter) -> Filter:
        """Returns a Filter instance from its configuration."""
        match filter_config.WhichOneof("filter"):
            case "all":
                return And()
            case "ref":
                return self._filter_by_name[filter_config.ref]
            case "not":
                return Not(self.parse(getattr(filter_config, "not")))
            case "and":
                return And(
                    *map(self.parse, getattr(filter_config, "and").filters)
                )
            case "or":
                return Or(
                    *map(self.parse, getattr(filter_config, "or").filters)
                )
            case "has_parts":
                return HasParts(filter_config.has_parts)
            case "custom_availability":
                return StringFieldMatcher(
                    lambda media_item: media_item.custom_availability,
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
