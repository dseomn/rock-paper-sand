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
from collections.abc import Mapping, Set
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


def from_config(
    filter_config: config_pb2.Filter,
    *,
    filter_by_name: Mapping[str, Filter],
) -> Filter:
    """Returns a Filter instance from its configuration.

    Args:
        filter_config: Config for the filter.
        filter_by_name: Other filters that are already defined.
    """
    recurse = functools.partial(from_config, filter_by_name=filter_by_name)
    match filter_config.WhichOneof("filter"):
        case "all":
            return And()
        case "ref":
            return filter_by_name[filter_config.ref]
        case "not":
            return Not(recurse(getattr(filter_config, "not")))
        case "and":
            return And(*map(recurse, getattr(filter_config, "and").filters))
        case "or":
            return Or(*map(recurse, getattr(filter_config, "or").filters))
        case _:
            raise ValueError(f"Unknown filter type: {filter_config!r}")
