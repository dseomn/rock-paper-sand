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
"""Code that uses JustWatch's API.

There doesn't seem to be much documentation of the API, but
https://github.com/dawoudt/JustWatchAPI shows some ways it can be used. This
file does not use that library because 1) the library doesn't seem to add much
value over doing plain REST calls, so it's probably not worth the extra
dependency, and 2) the library doesn't give enough control over the HTTP calls
to enable useful things like caching and retrying specific errors.
"""

import datetime
import dataclasses
import collections
from collections.abc import Collection, Iterable, Mapping, Set
import itertools
from typing import Any
import warnings

import cachecontrol.heuristics
import dateutil.parser
import requests

from rock_paper_sand import media_filter
from rock_paper_sand import multi_level_set
from rock_paper_sand import network
from rock_paper_sand.proto import config_pb2

_BASE_URL = "https://apis.justwatch.com/content"


def _parse_datetime(
    raw_value: str, *, relative_url: str
) -> datetime.datetime | None:
    value = dateutil.parser.isoparse(raw_value)
    if value in (datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc),):
        return None
    if value < datetime.datetime(1800, 1, 1, tzinfo=datetime.timezone.utc):
        # It looks like some of JustWatch's data uses the original release date
        # for the available_from field, despite the original release date being
        # before video streaming on the internet existed. From
        # https://en.wikipedia.org/wiki/Film#History it looks unlikely that any
        # original release date predates 1800 though.
        warnings.warn(
            f"{_BASE_URL}/{relative_url} has a date field that's improbably "
            f"old, {raw_value!r}. If it looks like it might be a placeholder, "
            "consider adding it to the _parse_datetime function.",
            UserWarning,
        )
    return value


class Api:
    """Wrapper around JustWatch's API."""

    def __init__(
        self,
        *,
        session: requests.Session,
        base_url: str = _BASE_URL,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._cache: dict[str, Any] = {}
        self._provider_name_by_short_name_by_locale: (
            dict[str, dict[str, str]]
        ) = {}

        # JustWatch seems to rate-limit the API enough to make this code pretty
        # slow when the requests are all cache misses, and they only tell
        # clients to cache for 10 minutes. Increasing that makes the code much
        # more responsive when called less often than every 10 minutes.
        self._session.mount(
            f"{self._base_url}/",
            network.requests_http_adapter(
                cache_heuristic=cachecontrol.heuristics.ExpiresAfter(hours=20)
            ),
        )

    def get(self, relative_url: str) -> Any:
        """Returns the decoded JSON response."""
        # While this cache *might* help with performance, the main reason to use
        # one here is to avoid race conditions. Without this, if a report were
        # generated around the time that data was expiring from the cachecontrol
        # cache, it would be possible for a section with {"justwatch": ...} and
        # another with {"not": {"justwatch": ...}} to either both match the same
        # media item or neither match the item. This cache makes sure that those
        # two filters see identical data, so that the mutual exclusion can be
        # preserved. NOTE: If this code is ever used in a long-running process,
        # this might need more work to avoid stale data.
        if relative_url in self._cache:
            return self._cache[relative_url]
        response = self._session.get(f"{self._base_url}/{relative_url}")
        response.raise_for_status()
        response_json = response.json()
        self._cache[relative_url] = response_json
        return response_json

    def post(self, relative_url: str, payload: Any) -> Any:
        """Returns the decoded JSON response to a POST request."""
        response = self._session.post(
            f"{self._base_url}/{relative_url}", json=payload
        )
        response.raise_for_status()
        return response.json()

    def locales(self) -> Collection[str]:
        """Returns the the JustWatch locale names."""
        return frozenset(
            locale["full_locale"] for locale in self.get("locales/state")
        )

    def providers(self, *, locale: str) -> Mapping[str, str]:
        """Returns a mapping from provider short name to human-readable name."""
        if locale not in self._provider_name_by_short_name_by_locale:
            self._provider_name_by_short_name_by_locale[locale] = {
                provider["short_name"]: provider["clear_name"]
                for provider in self.get(f"providers/locale/{locale}")
            }
        return self._provider_name_by_short_name_by_locale[locale]

    def provider_name(self, short_name: str, *, locale: str) -> str:
        """Returns the human-readable provider name."""
        return self.providers(locale=locale).get(short_name, short_name)

    def monetization_types(self, *, locale: str) -> Collection[str]:
        """Returns the monetization types."""
        return frozenset(
            itertools.chain.from_iterable(
                provider["monetization_types"]
                for provider in self.get(f"providers/locale/{locale}")
                if provider["monetization_types"] is not None
            )
        )


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Offer:
    provider_name: str
    comments: tuple[str, ...]


@dataclasses.dataclass(kw_only=True)
class _Availability:
    total_episode_count: int = 0
    episode_count_by_offer: collections.Counter[_Offer] = dataclasses.field(
        default_factory=collections.Counter
    )

    def update(self, other: "_Availability") -> None:
        self.total_episode_count += other.total_episode_count
        self.episode_count_by_offer.update(other.episode_count_by_offer)

    def to_extra_information(self) -> Set[str]:
        extra_information = set()
        for (
            offer,
            episode_count,
        ) in self.episode_count_by_offer.items():
            if episode_count == self.total_episode_count:
                comments = offer.comments
            else:
                comments = (
                    f"{episode_count}/{self.total_episode_count} episodes",
                    *offer.comments,
                )
            extra_information.add(
                f"{offer.provider_name} ({', '.join(comments)})"
            )
        return extra_information


def _content_number(content: Any) -> multi_level_set.MultiLevelNumber:
    parts = []
    for part_key in ("season_number", "episode_number"):
        if part_key in content:
            parts.append(content[part_key])
        else:
            break
    return multi_level_set.MultiLevelNumber(tuple(parts))


class Filter(media_filter.Filter):
    """Filter based on JustWatch's API."""

    def __init__(
        self,
        filter_config: config_pb2.JustWatchFilter,
        *,
        api: Api,
    ) -> None:
        self._config = filter_config
        self._api = api

    def _iter_episodes_and_relative_url(
        self,
        content: Any,
        *,
        exclude: multi_level_set.MultiLevelSet,
        relative_url: str,
    ) -> Iterable[tuple[Any, str]]:
        if _content_number(content) in exclude:
            return
        elif "seasons" in content:
            for season in content["seasons"]:
                if _content_number(season) in exclude:
                    continue
                season_relative_url = (
                    f"titles/{season['object_type']}/{season['id']}/locale/"
                    f"{self._config.locale}"
                )
                yield from self._iter_episodes_and_relative_url(
                    self._api.get(season_relative_url),
                    exclude=exclude,
                    relative_url=season_relative_url,
                )
        elif "episodes" in content:
            for episode in content["episodes"]:
                if _content_number(episode) in exclude:
                    continue
                yield episode, relative_url
        else:
            yield content, relative_url

    def _availability(
        self,
        content: Any,
        *,
        relative_url: str,
        now: datetime.datetime,
        done: multi_level_set.MultiLevelSet,
    ) -> _Availability:
        availability = _Availability(total_episode_count=1)
        for offer in content.get("offers", ()):
            provider = offer["package_short_name"]
            provider_name = self._api.provider_name(
                provider, locale=self._config.locale
            )
            monetization_type = offer["monetization_type"]
            if (
                self._config.providers
                and provider not in self._config.providers
            ) or (
                self._config.monetization_types
                and monetization_type not in self._config.monetization_types
            ):
                continue
            available_from = _parse_datetime(
                offer["available_from"], relative_url=relative_url
            )
            available_to = _parse_datetime(
                offer["available_to"], relative_url=relative_url
            )
            if available_to is not None and now > available_to:
                continue
            comments = [monetization_type]
            if available_from is not None and now < available_from:
                comments.append(f"starting {available_from}")
            if available_to is not None:
                comments.append(f"until {available_to}")
            availability.episode_count_by_offer[
                _Offer(provider_name=provider_name, comments=tuple(comments))
            ] = 1
        return availability

    def _all_done(
        self,
        content: Any,
        *,
        relative_url: str,
        done: multi_level_set.MultiLevelSet,
    ) -> bool:
        for _ in self._iter_episodes_and_relative_url(
            content, relative_url=relative_url, exclude=done
        ):
            return False
        return True

    def filter(
        self, media_item: config_pb2.MediaItem
    ) -> media_filter.FilterResult:
        """See base class."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        if not media_item.justwatch_id:
            return media_filter.FilterResult(False)
        done = multi_level_set.MultiLevelSet.from_string(media_item.done)
        relative_url = (
            f"titles/{media_item.justwatch_id}/locale/{self._config.locale}"
        )
        content = self._api.get(relative_url)
        extra_information: set[str] = set()
        if (
            self._config.providers
            or self._config.monetization_types
            or self._config.any_availability
        ):
            availability = _Availability()
            for (
                episode,
                episode_relative_url,
            ) in self._iter_episodes_and_relative_url(
                content,
                relative_url=relative_url,
                exclude=(
                    multi_level_set.MultiLevelSet(())
                    if self._config.include_done
                    else done
                ),
            ):
                availability.update(
                    self._availability(
                        episode,
                        relative_url=episode_relative_url,
                        now=now,
                        done=done,
                    )
                )
            if not availability.episode_count_by_offer:
                return media_filter.FilterResult(False)
            extra_information.update(availability.to_extra_information())
        if self._config.all_done and not self._all_done(
            content,
            done=done,
            relative_url=relative_url,
        ):
            return media_filter.FilterResult(False)
        return media_filter.FilterResult(True, extra=extra_information)
