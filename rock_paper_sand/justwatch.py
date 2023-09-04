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
from collections.abc import Set
from typing import Any
import warnings

import dateutil.parser
import requests

from rock_paper_sand import config_pb2
from rock_paper_sand import media_filter

_BASE_URL = "https://apis.justwatch.com/content"


def _parse_datetime(
    raw_value: str, *, relative_url: str
) -> datetime.datetime | None:
    value = dateutil.parser.isoparse(raw_value)
    if value in (datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc),):
        return None
    if value < datetime.datetime(1990, 1, 1, tzinfo=datetime.timezone.utc):
        # https://en.wikipedia.org/wiki/Video_on_demand says "As ... in the
        # 1990s ... which culminated in the arrival of VOD ..." so it seems
        # unlikely that any date before 1990 is valid in the context of when
        # JustWatch thinks something was available to stream online.
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
    ):
        self._session = session
        self._base_url = base_url
        self._cache = {}
        self._provider_name_by_short_name_by_locale = {}

    def get(self, relative_url: str) -> Any:
        """Returns the decoded JSON response."""
        if relative_url in self._cache:
            return self._cache[relative_url]
        response = self._session.get(f"{self._base_url}/{relative_url}")
        response.raise_for_status()
        response_json = response.json()
        self._cache[relative_url] = response_json
        return response_json

    def provider_name(self, short_name: str, *, locale: str) -> str:
        """Returns the human-readable provider name."""
        if locale not in self._provider_name_by_short_name_by_locale:
            self._provider_name_by_short_name_by_locale[locale] = {
                provider["short_name"]: provider["clear_name"]
                for provider in self.get(f"providers/locale/{locale}")
                if "clear_name" in provider
            }
        return self._provider_name_by_short_name_by_locale[locale].get(
            short_name, short_name
        )


class Filter(media_filter.Filter):
    """Filter based on JustWatch's API."""

    def __init__(
        self,
        filter_config: config_pb2.JustWatchFilter,
        *,
        api: Api,
    ):
        self._config = filter_config
        self._api = api

    def _availability(self, content: Any, *, relative_url: str) -> Set[str]:
        # TODO(dseomn): Detect and handle partial availability, e.g., when only
        # some seasons or episodes are available.
        availability = set()
        now = datetime.datetime.now(tz=datetime.timezone.utc)
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
            availability.add(f"{provider_name} ({', '.join(comments)})")
        return availability

    def filter(
        self, media_item: config_pb2.MediaItem
    ) -> media_filter.FilterResult:
        """See base class."""
        if not media_item.justwatch_id:
            return media_filter.FilterResult(False)
        relative_url = (
            f"titles/{media_item.justwatch_id}/locale/{self._config.locale}"
        )
        content = self._api.get(relative_url)
        extra_information = set()
        if (
            self._config.providers
            or self._config.monetization_types
            or self._config.any_availability
        ):
            availability = self._availability(
                content, relative_url=relative_url
            )
            if not availability:
                return media_filter.FilterResult(False)
            extra_information.update(availability)
        return media_filter.FilterResult(True, extra=extra_information)
