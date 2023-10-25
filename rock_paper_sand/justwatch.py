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
"""Code that uses JustWatch's API."""

import collections
from collections.abc import Collection, Generator, Iterable, Mapping, Set
import contextlib
import dataclasses
import datetime
from typing import Any

import dateutil.parser
import requests
import requests_cache

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import multi_level_set
from rock_paper_sand import network
from rock_paper_sand.proto import config_pb2

_GRAPHQL_URL = "https://apis.justwatch.com/graphql"


def _parse_datetime(raw_value: str | None) -> datetime.datetime | None:
    if raw_value is None:
        return None
    return dateutil.parser.isoparse(raw_value)


def _response_is_ok(response: requests.Response) -> bool:
    return "errors" not in response.json()


@contextlib.contextmanager
def requests_session() -> Generator[requests.Session, None, None]:
    """Returns a context manager for a session for the JustWatch API."""
    with requests_cache.CachedSession(
        **(
            network.requests_cache_defaults()
            | dict[str, Any](
                expire_after=datetime.timedelta(hours=20),
                cache_control=False,
                allowable_methods=("GET", "HEAD", "POST"),
                filter_fn=_response_is_ok,
            )
        ),
    ) as session:
        network.configure_session(session, additional_retry_methods=("POST",))
        yield session


class Api:
    """Wrapper around JustWatch's GraphQL API."""

    def __init__(
        self,
        *,
        session: requests.Session,
    ) -> None:
        self._session = session

        # While this cache *might* help with performance, the main reason to use
        # one here is to avoid race conditions. Without this, if a report were
        # generated around the time that data was expiring from the requests
        # cache, it would be possible for a section with {"justwatch": ...} and
        # another with {"not": {"justwatch": ...}} to either both match the same
        # media item or neither match the item. This cache makes sure that those
        # two filters see identical data, so that the mutual exclusion can be
        # preserved. NOTE: If this code is ever used in a long-running process,
        # this might need more work to avoid stale data.
        self._node_id_by_url_path: dict[str, str] = {}
        self._node_by_id_by_country: (
            dict[str, dict[str, Any]]
        ) = collections.defaultdict(dict)

    def query(
        self,
        document: str,
        *,
        operation_name: str,
        variables: Mapping[str, Any],
    ) -> Any:
        """Returns the result of a GraphQL query operation.

        Args:
            document: GraphQL document with at least one query.
            operation_name: Name of the query in the document to use.
            variables: Variables for the query.
        """
        response = self._session.post(
            _GRAPHQL_URL,
            json={
                "query": document,
                "operationName": operation_name,
                "variables": variables,
            },
        )
        with exceptions.add_note(f"Response body: {response.text}"):
            response.raise_for_status()
        response_json = response.json()
        if not _response_is_ok(response):
            raise ValueError(f"GraphQL query failed: {response_json}")
        return response_json

    def providers(self, *, country: str) -> Mapping[str, str]:
        """Returns a mapping from technical name to human-readable name."""
        result = self.query(
            """
            query GetProviders($country: Country!) {
                packages(
                    country: $country
                    platform: WEB
                    includeAddons: true
                ) {
                    technicalName
                    clearName
                }
            }
            """,
            operation_name="GetProviders",
            variables={"country": country},
        )
        return {
            package["technicalName"]: package["clearName"]
            for package in result["data"]["packages"]
        }

    def monetization_types(self, *, country: str) -> Collection[str]:
        """Returns the monetization types."""
        result = self.query(
            """
            query GetMonetizationTypes($country: Country!) {
                packages(
                    country: $country
                    platform: WEB
                    includeAddons: true
                ) {
                    monetizationTypes
                }
            }
            """,
            operation_name="GetMonetizationTypes",
            variables={"country": country},
        )
        monetization_types: set[str] = set()
        for package in result["data"]["packages"]:
            monetization_types.update(
                monetization_type.lower()
                for monetization_type in package["monetizationTypes"]
            )
        return monetization_types

    def get_node(self, node_id_or_url: str, *, country: str) -> Any:
        """Returns a node (e.g., movie or TV show)."""
        query_document = """
        fragment Episode on Episode {
            __typename
            id
            # JustWatch seems to need a language for the seasonNumber and
            # episodeNumber, but the language also doesn't seem to have any
            # effect on them. So this uses a syntactically valid but nonexistent
            # language.
            content(country: $country, language: "qa-INVALID") {
                seasonNumber
                episodeNumber
            }
            offers(country: $country, platform: WEB) {
                monetizationType
                availableToTime
                availableFromTime
                package {
                    clearName
                    technicalName
                }
            }
        }

        fragment Season on Season {
            __typename
            id
            content(country: $country, language: "qa-INVALID") {
                seasonNumber
            }
            episodes {
                ...Episode
            }
        }

        fragment Show on Show {
            __typename
            id
            seasons {
                ...Season
            }
        }

        fragment Movie on Movie {
            __typename
            id
            offers(country: $country, platform: WEB) {
                monetizationType
                availableToTime
                availableFromTime
                package {
                    clearName
                    technicalName
                }
            }
        }

        fragment Node on Node {
            __typename
            id
            ...Episode
            ...Season
            ...Show
            ...Movie
        }

        query GetNodeById($nodeId: ID!, $country: Country!) {
            node(id: $nodeId) {
                ...Node
            }
        }

        query GetNodeByUrlPath($urlPath: String!, $country: Country!) {
            urlV2(fullPath: $urlPath) {
                node {
                    ...Node
                }
            }
        }
        """
        node_by_id = self._node_by_id_by_country[country]
        if (
            url_path := node_id_or_url.removeprefix("https://www.justwatch.com")
        ).startswith("/"):
            if url_path not in self._node_id_by_url_path:
                node = self.query(
                    query_document,
                    operation_name="GetNodeByUrlPath",
                    variables={
                        "urlPath": url_path,
                        "country": country,
                    },
                )["data"]["urlV2"]["node"]
                self._node_id_by_url_path[url_path] = node["id"]
                node_by_id.setdefault(node["id"], node)
            node_id = self._node_id_by_url_path[url_path]
        else:
            node_id = node_id_or_url
        if node_id not in node_by_id:
            node_by_id[node_id] = self.query(
                query_document,
                operation_name="GetNodeById",
                variables={
                    "nodeId": node_id,
                    "country": country,
                },
            )["data"]["node"]
        return node_by_id[node_id]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Offer:
    provider_name: str
    comments: tuple[str, ...]


class _OfferResultExtra(media_filter.ResultExtra):
    PROVIDER = "justwatch.provider"
    COMMENTS = "justwatch._comments"
    PUBLIC_KEYS = (PROVIDER,)

    def human_readable(self) -> str | None:
        """See base class."""
        return f"{self[self.PROVIDER]} ({', '.join(self[self.COMMENTS])})"


@dataclasses.dataclass(kw_only=True)
class _Availability:
    """Per-episode availability of a media item."""

    total_episode_count: int = 0
    episode_count_by_offer: collections.Counter[_Offer] = dataclasses.field(
        default_factory=collections.Counter
    )

    def update(self, other: "_Availability") -> None:
        """Adds another _Availability into this one."""
        self.total_episode_count += other.total_episode_count
        self.episode_count_by_offer.update(other.episode_count_by_offer)

    def to_extra_information(self) -> Set[media_filter.ResultExtra]:
        """Returns availability info for the FilterResult.extra field."""
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
                _OfferResultExtra(
                    {
                        _OfferResultExtra.PROVIDER: offer.provider_name,
                        _OfferResultExtra.COMMENTS: comments,
                    }
                )
            )
        return extra_information


def _content_number(node: Any) -> multi_level_set.MultiLevelNumber:
    content = node.get("content", {})
    parts = []
    for part_key in ("seasonNumber", "episodeNumber"):
        if part_key in content:
            parts.append(content[part_key])
        else:
            break
    return multi_level_set.MultiLevelNumber(tuple(parts))


class Filter(media_filter.CachedFilter):
    """Filter based on JustWatch's API."""

    def __init__(
        self,
        filter_config: config_pb2.JustWatchFilter,
        *,
        api: Api,
    ) -> None:
        super().__init__()
        self._config = filter_config
        self._api = api
        if not self._config.country:
            raise ValueError("The country field is required.")

    def _should_check_availability(self) -> bool:
        return bool(
            self._config.providers
            or self._config.monetization_types
            or self._config.any_availability
        )

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        keys: set[str] = set()
        if self._should_check_availability():
            keys.update(_OfferResultExtra.PUBLIC_KEYS)
        return keys

    def _iter_leaf_nodes(
        self,
        node: Any,
        *,
        exclude: multi_level_set.MultiLevelSet,
    ) -> Iterable[Any]:
        if _content_number(node) in exclude:
            return
        elif "seasons" in node:
            for season in node["seasons"]:
                yield from self._iter_leaf_nodes(season, exclude=exclude)
        elif "episodes" in node:
            for episode in node["episodes"]:
                yield from self._iter_leaf_nodes(episode, exclude=exclude)
        else:
            yield node

    def _leaf_node_availability(
        self,
        node: Any,
        *,
        now: datetime.datetime,
        not_available_after: datetime.datetime | None,
    ) -> _Availability:
        availability = _Availability(total_episode_count=1)
        for offer in node.get("offers", ()):
            provider = offer["package"]["technicalName"]
            provider_name = offer["package"]["clearName"]
            monetization_type = offer["monetizationType"].lower()
            if (
                self._config.providers
                and provider not in self._config.providers
            ) or (
                self._config.monetization_types
                and monetization_type not in self._config.monetization_types
            ):
                continue
            available_from = _parse_datetime(offer["availableFromTime"])
            available_to = _parse_datetime(offer["availableToTime"])
            if available_to is not None and now > available_to:
                continue
            if not_available_after is not None and (
                available_to is None or available_to > not_available_after
            ):
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

    def _availability(
        self,
        node: Any,
        *,
        request: media_filter.FilterRequest,
    ) -> _Availability:
        not_available_after = (
            request.now
            + datetime.timedelta(days=self._config.not_available_after_days)
            if self._config.HasField("not_available_after_days")
            else None
        )
        availability = _Availability()
        for leaf_node in self._iter_leaf_nodes(
            node,
            exclude=(
                multi_level_set.MultiLevelSet(())
                if self._config.include_done
                else request.item.done
            ),
        ):
            availability.update(
                self._leaf_node_availability(
                    leaf_node,
                    now=request.now,
                    not_available_after=not_available_after,
                )
            )
        return availability

    def _all_done(
        self,
        node: Any,
        *,
        done: multi_level_set.MultiLevelSet,
    ) -> bool:
        for _ in self._iter_leaf_nodes(node, exclude=done):
            return False
        return True

    def filter_implementation(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        with exceptions.add_note(
            f"While filtering {request.item.debug_description} using JustWatch "
            f"filter config:\n{self._config}"
        ):
            if not request.item.proto.justwatch:
                return media_filter.FilterResult(False)
            node = self._api.get_node(
                request.item.proto.justwatch, country=self._config.country
            )
            extra_information: set[media_filter.ResultExtra] = set()
            if self._should_check_availability():
                availability = self._availability(node, request=request)
                if not availability.episode_count_by_offer:
                    return media_filter.FilterResult(False)
                extra_information.update(availability.to_extra_information())
            if self._config.all_done and not self._all_done(
                node,
                done=request.item.done,
            ):
                return media_filter.FilterResult(False)
            return media_filter.FilterResult(True, extra=extra_information)
