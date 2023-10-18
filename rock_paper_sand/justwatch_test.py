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

# pylint: disable=missing-module-docstring

from collections.abc import Mapping, Set
import datetime
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict
import requests

from rock_paper_sand import justwatch
from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand.proto import config_pb2

_NOW = datetime.datetime.now(tz=datetime.timezone.utc)
_TIME_IN_PAST_1 = _NOW - datetime.timedelta(days=1)
_TIME_IN_FUTURE_1 = _NOW + datetime.timedelta(days=1)
_TIME_IN_FUTURE_2 = _NOW + datetime.timedelta(days=2)


def _offer(
    *,
    monetization_type: str = "some_monetization_type",
    available_to: str | None = None,
    available_from: str | None = None,
    package_technical_name: str = "some_package",
) -> Any:
    return {
        "monetizationType": monetization_type.upper(),
        "availableToTime": available_to,
        "availableFromTime": available_from,
        "package": {
            "clearName": f"{package_technical_name.capitalize()}+",
            "technicalName": package_technical_name,
        },
    }


def _offer_extra(
    provider: str,
    comments: tuple[str, ...],
) -> justwatch._OfferResultExtra:
    return justwatch._OfferResultExtra(  # pylint: disable=protected-access
        {
            justwatch._OfferResultExtra.PROVIDER: provider,  # pylint: disable=protected-access
            justwatch._OfferResultExtra.COMMENTS: comments,  # pylint: disable=protected-access
        }
    )


class JustWatchSessionTest(parameterized.TestCase):
    def test_session(self) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        with justwatch.requests_session() as session:
            self.assertIsInstance(session, requests.Session)


class JustWatchApiTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_session = mock.create_autospec(
            requests.Session, spec_set=True, instance=True
        )
        self._api = justwatch.Api(session=self._mock_session)

    def test_query(self) -> None:
        self._mock_session.post.return_value.json.return_value = "some-result"

        result = self._api.query(
            "some-document",
            operation_name="SomeOperation",
            variables={"foo": "bar"},
        )

        self.assertEqual("some-result", result)
        self.assertContainsSubsequence(
            self._mock_session.mock_calls,
            (
                mock.call.post(
                    mock.ANY,
                    json={
                        "query": "some-document",
                        "operationName": "SomeOperation",
                        "variables": {"foo": "bar"},
                    },
                ),
                # There's a call to mock.call.post().text.__str__() here that's
                # a bit hard to test for, and not that important.
                mock.call.post().raise_for_status(),
                mock.call.post().json(),
            ),
        )

    def test_query_graphql_errors(self) -> None:
        self._mock_session.post.return_value.json.return_value = {
            "errors": "some-error"
        }

        with self.assertRaisesRegex(ValueError, "some-error"):
            self._api.query(
                "some-document",
                operation_name="SomeOperation",
                variables={},
            )

    def test_providers(self) -> None:
        self._mock_session.post.return_value.json.return_value = {
            "data": {
                "packages": [{"technicalName": "foo", "clearName": "Foo+"}]
            }
        }

        providers = self._api.providers(country="US")

        self.assertEqual({"foo": "Foo+"}, providers)
        self._mock_session.post.assert_called_once()

    def test_monetization_types(self) -> None:
        self._mock_session.post.return_value.json.return_value = {
            "data": {
                "packages": [
                    {"monetizationTypes": ["FOO"]},
                    {"monetizationTypes": ["BAR", "QUUX"]},
                ]
            }
        }

        monetization_types = self._api.monetization_types(country="US")

        self.assertCountEqual(("foo", "bar", "quux"), monetization_types)
        self._mock_session.post.assert_called_once()

    @parameterized.named_parameters(
        dict(
            testcase_name="url_full",
            node_id_or_url="https://www.justwatch.com/some-url",
            operation_name="GetNodeByUrlPath",
            variables={"urlPath": "/some-url", "country": "US"},
            json_response={"data": {"urlV2": {"node": {"id": "some-id"}}}},
        ),
        dict(
            testcase_name="url_path",
            node_id_or_url="/some-url",
            operation_name="GetNodeByUrlPath",
            variables={"urlPath": "/some-url", "country": "US"},
            json_response={"data": {"urlV2": {"node": {"id": "some-id"}}}},
        ),
        dict(
            testcase_name="node_id",
            node_id_or_url="some-id",
            operation_name="GetNodeById",
            variables={"nodeId": "some-id", "country": "US"},
            json_response={"data": {"node": {"id": "some-id"}}},
        ),
    )
    def test_get_node(
        self,
        *,
        node_id_or_url: str,
        operation_name: str,
        variables: Mapping[str, Any],
        json_response: Any,
    ) -> None:
        self._mock_session.post.return_value.json.return_value = json_response

        node = self._api.get_node(node_id_or_url, country="US")

        self.assertEqual({"id": "some-id"}, node)
        self._mock_session.post.assert_called_once_with(
            mock.ANY,
            json={
                "query": mock.ANY,
                "operationName": operation_name,
                "variables": variables,
            },
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="url_path",
            node_id_or_url="/some-url",
            json_response={"data": {"urlV2": {"node": {"id": "some-id"}}}},
        ),
        dict(
            testcase_name="node_id",
            node_id_or_url="some-id",
            json_response={"data": {"node": {"id": "some-id"}}},
        ),
    )
    def test_get_node_cached(
        self,
        *,
        node_id_or_url: str,
        json_response: Any,
    ) -> None:
        self._mock_session.post.return_value.json.return_value = json_response
        self._api.get_node(node_id_or_url, country="US")
        self._mock_session.reset_mock()

        node = self._api.get_node(node_id_or_url, country="US")

        self.assertEqual({"id": "some-id"}, node)
        self.assertEmpty(self._mock_session.mock_calls)

    def test_get_node_by_url_path_with_cache_by_node_id(self) -> None:
        self._mock_session.post.return_value.json.return_value = {
            "data": {"node": {"id": "some-id", "foo": "old-value"}}
        }
        self._api.get_node("some-id", country="US")
        self._mock_session.reset_mock()
        self._mock_session.post.return_value.json.return_value = {
            "data": {"urlV2": {"node": {"id": "some-id", "foo": "new-value"}}}
        }

        node = self._api.get_node("/some-url", country="US")

        self.assertEqual({"id": "some-id", "foo": "old-value"}, node)
        self._mock_session.post.assert_called_once_with(
            mock.ANY,
            json={
                "query": mock.ANY,
                "operationName": "GetNodeByUrlPath",
                "variables": {"urlPath": "/some-url", "country": "US"},
            },
        )

    def test_get_node_by_url_path_with_cache_in_other_country(self) -> None:
        self._mock_session.post.return_value.json.return_value = {
            "data": {"urlV2": {"node": {"id": "some-id", "foo": "CA-value"}}}
        }
        self._api.get_node("/some-url", country="CA")
        self._mock_session.reset_mock()
        self._mock_session.post.return_value.json.return_value = {
            "data": {"node": {"id": "some-id", "foo": "US-value"}}
        }

        node = self._api.get_node("/some-url", country="US")

        self.assertEqual({"id": "some-id", "foo": "US-value"}, node)
        self._mock_session.post.assert_called_once_with(
            mock.ANY,
            json={
                "query": mock.ANY,
                "operationName": "GetNodeById",
                "variables": {"nodeId": "some-id", "country": "US"},
            },
        )


class FilterTest(parameterized.TestCase):
    def setUp(self) -> None:
        self._mock_api = mock.create_autospec(
            justwatch.Api, spec_set=True, instance=True
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="no_url",
            filter_config={"country": "US"},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={"country": "US"},
            item={"name": "foo", "justwatch": "tm1"},
            api_data={("tm1", "US"): {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="any_availability_no_match",
            filter_config={"country": "US", "anyAvailability": True},
            item={"name": "foo", "justwatch": "tm1"},
            api_data={("tm1", "US"): {}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="any_availability_matches",
            filter_config={"country": "US", "anyAvailability": True},
            item={"name": "foo", "justwatch": "tm1"},
            api_data={
                ("tm1", "US"): {
                    "offers": [
                        _offer(
                            package_technical_name="foo",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_technical_name="quux",
                            monetization_type="baz",
                            available_from=_TIME_IN_FUTURE_1.isoformat(),
                            available_to=_TIME_IN_FUTURE_2.isoformat(),
                        ),
                        _offer(available_to=_TIME_IN_PAST_1.isoformat()),
                    ],
                },
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    _offer_extra("Foo+", ("bar",)),
                    _offer_extra(
                        "Quux+",
                        (
                            "baz",
                            f"starting {_TIME_IN_FUTURE_1}",
                            f"until {_TIME_IN_FUTURE_2}",
                        ),
                    ),
                },
            ),
        ),
        dict(
            testcase_name="specific_availability_matches",
            filter_config={
                "country": "US",
                "providers": ["foo"],
                "monetizationTypes": ["bar"],
            },
            item={"name": "foo", "justwatch": "tm1"},
            api_data={
                ("tm1", "US"): {
                    "offers": [
                        _offer(
                            package_technical_name="foo",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_technical_name="hidden",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_technical_name="foo",
                            monetization_type="hidden",
                        ),
                        _offer(
                            package_technical_name="hidden",
                            monetization_type="hidden",
                        ),
                    ],
                },
            },
            expected_result=media_filter.FilterResult(
                True, extra={_offer_extra("Foo+", ("bar",))}
            ),
        ),
        dict(
            testcase_name="partial_availability",
            filter_config={"country": "US", "anyAvailability": True},
            item={"name": "foo", "justwatch": "ts1"},
            api_data={
                ("ts1", "US"): {
                    "seasons": [
                        {
                            "episodes": [
                                {
                                    "offers": [
                                        _offer(
                                            package_technical_name="foo",
                                            monetization_type="bar",
                                        ),
                                    ],
                                },
                                {
                                    # This represents an episode that's
                                    # unavailable.
                                },
                            ],
                        },
                        {
                            # This represents an upcoming season with no
                            # episodes yet.
                        },
                    ],
                },
            },
            expected_result=media_filter.FilterResult(
                True,
                # Showing "1/3 episodes" isn't ideal because it counts the
                # upcoming season as an episode, but I'm not sure it's worth the
                # effort to improve it.
                extra={_offer_extra("Foo+", ("1/3 episodes", "bar"))},
            ),
        ),
        dict(
            testcase_name="exclude_done",
            filter_config={
                "country": "US",
                "includeDone": False,
                "anyAvailability": True,
            },
            item={"name": "foo", "done": "all", "justwatch": "tm1"},
            api_data={("tm1", "US"): {"offers": [_offer()]}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="exclude_done_partial",
            filter_config={
                "country": "US",
                "includeDone": False,
                "anyAvailability": True,
            },
            item={
                "name": "foo",
                "done": "1-2.1",
                "justwatch": "ts1",
            },
            api_data={
                ("ts1", "US"): {
                    "seasons": [
                        {
                            "content": {"seasonNumber": 1},
                            "episodes": [
                                {
                                    "content": {
                                        "seasonNumber": 1,
                                        "episodeNumber": 1,
                                    },
                                    "offers": [_offer()],
                                },
                            ],
                        },
                        {
                            "content": {"seasonNumber": 2},
                            "episodes": [
                                {
                                    "content": {
                                        "seasonNumber": 2,
                                        "episodeNumber": 1,
                                    },
                                },
                                {
                                    "content": {
                                        "seasonNumber": 2,
                                        "episodeNumber": 2,
                                    },
                                },
                                {
                                    "content": {
                                        "seasonNumber": 2,
                                        "episodeNumber": 3,
                                    },
                                    "offers": [
                                        _offer(
                                            package_technical_name="foo",
                                            monetization_type="bar",
                                        ),
                                    ],
                                },
                            ],
                        },
                    ],
                },
            },
            expected_result=media_filter.FilterResult(
                True, extra={_offer_extra("Foo+", ("1/2 episodes", "bar"))}
            ),
        ),
        dict(
            testcase_name="include_done",
            filter_config={
                "country": "US",
                "includeDone": True,
                "anyAvailability": True,
            },
            item={"name": "foo", "done": "all", "justwatch": "tm1"},
            api_data={
                ("tm1", "US"): {
                    "offers": [
                        _offer(
                            package_technical_name="foo",
                            monetization_type="bar",
                        )
                    ],
                }
            },
            expected_result=media_filter.FilterResult(
                True, extra={_offer_extra("Foo+", ("bar",))}
            ),
        ),
        dict(
            testcase_name="not_available_after",
            filter_config={
                "country": "US",
                "notAvailableAfterDays": 1.5,
                "anyAvailability": True,
            },
            item={"name": "foo", "justwatch": "tm1"},
            api_data={
                ("tm1", "US"): {
                    "offers": [
                        _offer(
                            package_technical_name="foo",
                            monetization_type="bar",
                            available_to=_TIME_IN_FUTURE_1.isoformat(),
                        ),
                        _offer(available_to=_TIME_IN_FUTURE_2.isoformat()),
                        _offer(),
                    ],
                }
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    _offer_extra("Foo+", ("bar", f"until {_TIME_IN_FUTURE_1}"))
                },
            ),
        ),
        dict(
            testcase_name="all_done_true",
            filter_config={
                "country": "US",
                "allDone": True,
            },
            item={
                "name": "foo",
                "done": "1-2.1",
                "justwatch": "ts1",
            },
            api_data={
                ("ts1", "US"): {
                    "seasons": [
                        {
                            "content": {"seasonNumber": 1},
                            "episodes": [
                                {
                                    "content": {
                                        "seasonNumber": 1,
                                        "episodeNumber": 1,
                                    },
                                },
                            ],
                        },
                        {
                            "content": {"seasonNumber": 2},
                            "episodes": [
                                {
                                    "content": {
                                        "seasonNumber": 2,
                                        "episodeNumber": 1,
                                    },
                                },
                            ],
                        },
                    ],
                },
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="all_done_false",
            filter_config={
                "country": "US",
                "allDone": True,
            },
            item={"name": "foo", "done": "1.1", "justwatch": "ts1"},
            api_data={
                ("ts1", "US"): {
                    "seasons": [
                        {
                            "content": {"seasonNumber": 1},
                            "episodes": [
                                {
                                    "content": {
                                        "seasonNumber": 1,
                                        "episodeNumber": 1,
                                    },
                                },
                                {
                                    "content": {
                                        "seasonNumber": 1,
                                        "episodeNumber": 2,
                                    },
                                },
                            ],
                        },
                    ],
                },
            },
            expected_result=media_filter.FilterResult(False),
        ),
    )
    def test_filter(
        self,
        *,
        filter_config: Any,
        item: Any,
        api_data: Mapping[tuple[str, str], Any] = immutabledict.immutabledict(),
        expected_result: media_filter.FilterResult,
    ) -> None:
        self._mock_api.get_node.side_effect = (
            lambda node_id_or_url, country: api_data[(node_id_or_url, country)]
        )
        test_filter = justwatch.Filter(
            json_format.ParseDict(filter_config, config_pb2.JustWatchFilter()),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_filter.FilterRequest(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(item, config_pb2.MediaItem())
                )
            )
        )

        self.assertEqual(expected_result, result)

    @parameterized.named_parameters(
        dict(
            testcase_name="no_match_conditions",
            filter_config={"country": "US"},
            valid_extra_keys=frozenset(),
        ),
        dict(
            testcase_name="availability_conditions",
            filter_config={"country": "US", "anyAvailability": True},
            valid_extra_keys={"justwatch.provider"},
        ),
    )
    def test_valid_extra_keys(
        self,
        *,
        filter_config: Any,
        valid_extra_keys: Set[str],
    ) -> None:
        test_filter = justwatch.Filter(
            json_format.ParseDict(filter_config, config_pb2.JustWatchFilter()),
            api=self._mock_api,
        )
        self.assertEqual(valid_extra_keys, test_filter.valid_extra_keys())

    def test_missing_country_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "country"):
            justwatch.Filter(config_pb2.JustWatchFilter(), api=self._mock_api)

    def test_exception_note(self) -> None:
        self._mock_api.get_node.side_effect = ValueError("kumquat")
        test_filter = justwatch.Filter(
            json_format.ParseDict(
                {"country": "US"}, config_pb2.JustWatchFilter()
            ),
            api=self._mock_api,
        )

        with self.assertRaisesRegex(ValueError, "kumquat") as error:
            test_filter.filter(
                media_filter.FilterRequest(
                    media_item.MediaItem.from_config(
                        json_format.ParseDict(
                            {"name": "foo", "justwatch": "tm1"},
                            config_pb2.MediaItem(),
                        )
                    )
                )
            )
        self.assertSequenceEqual(
            (
                "While filtering unknown media item with name 'foo' using "
                'JustWatch filter config:\ncountry: "US"\n',
            ),
            error.exception.__notes__,
        )

    def test_extra_human_readable(self) -> None:
        self._mock_api.get_node.return_value = {
            "offers": [
                _offer(
                    package_technical_name="foo",
                    monetization_type="bar",
                    available_to=_TIME_IN_FUTURE_1.isoformat(),
                )
            ],
        }
        test_filter = justwatch.Filter(
            json_format.ParseDict(
                {"country": "US", "anyAvailability": True},
                config_pb2.JustWatchFilter(),
            ),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_filter.FilterRequest(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(
                        {"name": "foo", "justwatch": "tm1"},
                        config_pb2.MediaItem(),
                    )
                )
            )
        )

        self.assertEqual(
            {f"Foo+ (bar, until {_TIME_IN_FUTURE_1})"},
            {extra.human_readable() for extra in result.extra},
        )


if __name__ == "__main__":
    absltest.main()
