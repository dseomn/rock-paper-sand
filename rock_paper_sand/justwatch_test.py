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
    package_short_name: str = "some_package",
    monetization_type: str = "some_monetization_type",
    available_from: str = "0001-01-01T00:00:00Z",
    available_to: str = "0001-01-01T00:00:00Z",
) -> Any:
    return {
        "package_short_name": package_short_name,
        "monetization_type": monetization_type,
        "available_from": available_from,
        "available_to": available_to,
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
        self.assertSequenceEqual(
            (
                mock.call.post(
                    mock.ANY,
                    json={
                        "query": "some-document",
                        "operationName": "SomeOperation",
                        "variables": {"foo": "bar"},
                    },
                ),
                mock.call.post().raise_for_status(),
                mock.call.post().json(),
            ),
            self._mock_session.mock_calls,
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


class JustWatchObsoleteApiTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_session = mock.create_autospec(
            requests.Session, spec_set=True, instance=True
        )
        self._base_url = "http://localhost"
        self._api = justwatch.ObsoleteApi(
            session=self._mock_session, base_url=self._base_url
        )
        self._mock_session.reset_mock()

    def test_get(self) -> None:
        self._mock_session.get.return_value.json.return_value = "foo"

        data = self._api.get("bar")

        self.assertEqual("foo", data)
        self.assertSequenceEqual(
            (
                mock.call.get(f"{self._base_url}/bar"),
                mock.call.get().raise_for_status(),
                mock.call.get().json(),
            ),
            self._mock_session.mock_calls,
        )

    def test_cache(self) -> None:
        self._mock_session.get.return_value.json.return_value = "foo"
        self._api.get("bar")
        self._mock_session.reset_mock()

        data = self._api.get("bar")

        self.assertEqual("foo", data)
        self.assertEmpty(self._mock_session.mock_calls)

    def test_providers(self) -> None:
        self._mock_session.get.return_value.json.return_value = [
            {"short_name": "foo", "clear_name": "Foo+"},
        ]

        providers = self._api.providers(locale="en_US")

        self.assertEqual({"foo": "Foo+"}, providers)
        self._mock_session.get.assert_called_once_with(
            f"{self._base_url}/providers/locale/en_US"
        )

    def test_providers_cached(self) -> None:
        self._mock_session.get.return_value.json.return_value = [
            {"short_name": "foo", "clear_name": "Foo+"},
        ]
        self._api.providers(locale="en_US")
        self._mock_session.reset_mock()

        providers = self._api.providers(locale="en_US")

        self.assertEqual({"foo": "Foo+"}, providers)
        self.assertEmpty(self._mock_session.mock_calls)

    def test_provider_name(self) -> None:
        self._mock_session.get.return_value.json.return_value = [
            {"short_name": "foo", "clear_name": "Foo+"},
        ]

        provider_name = self._api.provider_name("foo", locale="en_US")

        self.assertEqual("Foo+", provider_name)

    def test_provider_name_not_found(self) -> None:
        self._mock_session.get.return_value.json.return_value = []
        self.assertEqual("foo", self._api.provider_name("foo", locale="en_US"))


class FilterTest(parameterized.TestCase):
    def setUp(self) -> None:
        self._mock_api = mock.create_autospec(
            justwatch.ObsoleteApi, spec_set=True, instance=True
        )
        self._mock_api.provider_name.side_effect = (
            lambda short_name, locale: f"{short_name.capitalize()}+"
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="no_id",
            filter_config={"locale": "en_US"},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={"locale": "en_US"},
            item={"name": "foo", "justwatchId": "movie/1"},
            api_data={"titles/movie/1/locale/en_US": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="any_availability_no_match",
            filter_config={"locale": "en_US", "anyAvailability": True},
            item={"name": "foo", "justwatchId": "movie/1"},
            api_data={"titles/movie/1/locale/en_US": {}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="any_availability_matches",
            filter_config={"locale": "en_US", "anyAvailability": True},
            item={"name": "foo", "justwatchId": "movie/1"},
            api_data={
                "titles/movie/1/locale/en_US": {
                    "offers": [
                        _offer(
                            package_short_name="foo",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_short_name="quux",
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
                "locale": "en_US",
                "providers": ["foo"],
                "monetizationTypes": ["bar"],
            },
            item={"name": "foo", "justwatchId": "movie/1"},
            api_data={
                "titles/movie/1/locale/en_US": {
                    "offers": [
                        _offer(
                            package_short_name="foo",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_short_name="hidden",
                            monetization_type="bar",
                        ),
                        _offer(
                            package_short_name="foo",
                            monetization_type="hidden",
                        ),
                        _offer(
                            package_short_name="hidden",
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
            filter_config={"locale": "en_US", "anyAvailability": True},
            item={"name": "foo", "justwatchId": "show/1"},
            api_data={
                "titles/show/1/locale/en_US": {
                    "seasons": [
                        {"object_type": "show_season", "id": 1},
                        {"object_type": "show_season", "id": 2},
                    ],
                },
                "titles/show_season/1/locale/en_US": {
                    "episodes": [
                        {
                            "offers": [
                                _offer(
                                    package_short_name="foo",
                                    monetization_type="bar",
                                ),
                            ],
                        },
                        {
                            # This represents an episode that's unavailable.
                        },
                    ],
                },
                "titles/show_season/2/locale/en_US": {
                    # This represents an upcoming season with no episodes yet.
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
                "locale": "en_US",
                "includeDone": False,
                "anyAvailability": True,
            },
            item={"name": "foo", "done": "all", "justwatchId": "movie/1"},
            api_data={"titles/movie/1/locale/en_US": {"offers": [_offer()]}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="exclude_done_partial",
            filter_config={
                "locale": "en_US",
                "includeDone": False,
                "anyAvailability": True,
            },
            item={
                "name": "foo",
                "done": "1-2.1",
                "justwatchId": "show/1",
            },
            api_data={
                "titles/show/1/locale/en_US": {
                    "seasons": [
                        {
                            "object_type": "show_season",
                            "id": 1,
                            "season_number": 1,
                        },
                        {
                            "object_type": "show_season",
                            "id": 2,
                            "season_number": 2,
                        },
                    ],
                },
                "titles/show_season/2/locale/en_US": {
                    "season_number": 2,
                    "episodes": [
                        {"season_number": 2, "episode_number": 1},
                        {"season_number": 2, "episode_number": 2},
                        {
                            "season_number": 2,
                            "episode_number": 3,
                            "offers": [
                                _offer(
                                    package_short_name="foo",
                                    monetization_type="bar",
                                ),
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
                "locale": "en_US",
                "includeDone": True,
                "anyAvailability": True,
            },
            item={"name": "foo", "done": "all", "justwatchId": "movie/1"},
            api_data={
                "titles/movie/1/locale/en_US": {
                    "offers": [
                        _offer(
                            package_short_name="foo",
                            monetization_type="bar",
                        )
                    ]
                }
            },
            expected_result=media_filter.FilterResult(
                True, extra={_offer_extra("Foo+", ("bar",))}
            ),
        ),
        dict(
            testcase_name="not_available_after",
            filter_config={
                "locale": "en_US",
                "notAvailableAfterDays": 1.5,
                "anyAvailability": True,
            },
            item={"name": "foo", "justwatchId": "movie/1"},
            api_data={
                "titles/movie/1/locale/en_US": {
                    "offers": [
                        _offer(
                            package_short_name="foo",
                            monetization_type="bar",
                            available_to=_TIME_IN_FUTURE_1.isoformat(),
                        ),
                        _offer(available_to=_TIME_IN_FUTURE_2.isoformat()),
                        _offer(),
                    ]
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
                "locale": "en_US",
                "allDone": True,
            },
            item={
                "name": "foo",
                "done": "1-2.1",
                "justwatchId": "show/1",
            },
            api_data={
                "titles/show/1/locale/en_US": {
                    "seasons": [
                        {
                            "object_type": "show_season",
                            "id": 1,
                            "season_number": 1,
                        },
                        {
                            "object_type": "show_season",
                            "id": 2,
                            "season_number": 2,
                        },
                    ],
                },
                "titles/show_season/2/locale/en_US": {
                    "season_number": 2,
                    "episodes": [
                        {"season_number": 2, "episode_number": 1},
                    ],
                },
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="all_done_false",
            filter_config={
                "locale": "en_US",
                "allDone": True,
            },
            item={"name": "foo", "done": "1.1", "justwatchId": "show/1"},
            api_data={
                "titles/show/1/locale/en_US": {
                    "seasons": [
                        {"object_type": "show_season", "id": 1},
                    ],
                },
                "titles/show_season/1/locale/en_US": {
                    "episodes": [
                        {"season_number": 1, "episode_number": 1},
                        {"season_number": 1, "episode_number": 2},
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
        api_data: Mapping[str, Any] = immutabledict.immutabledict(),
        expected_result: media_filter.FilterResult,
    ) -> None:
        self._mock_api.get.side_effect = lambda relative_url: api_data[
            relative_url
        ]
        test_filter = justwatch.Filter(
            json_format.ParseDict(filter_config, config_pb2.JustWatchFilter()),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_item.MediaItem.from_config(
                json_format.ParseDict(item, config_pb2.MediaItem())
            )
        )

        self.assertEqual(expected_result, result)

    @parameterized.named_parameters(
        dict(
            testcase_name="no_match_conditions",
            filter_config={"locale": "en_US"},
            valid_extra_keys=frozenset(),
        ),
        dict(
            testcase_name="availability_conditions",
            filter_config={"locale": "en_US", "anyAvailability": True},
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

    def test_missing_locale_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "locale"):
            justwatch.Filter(config_pb2.JustWatchFilter(), api=self._mock_api)

    def test_exception_note(self) -> None:
        self._mock_api.get.side_effect = ValueError("kumquat")
        test_filter = justwatch.Filter(
            json_format.ParseDict(
                {"locale": "en_US"}, config_pb2.JustWatchFilter()
            ),
            api=self._mock_api,
        )

        with self.assertRaisesRegex(ValueError, "kumquat") as error:
            test_filter.filter(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(
                        {"name": "foo", "justwatchId": "movie/1"},
                        config_pb2.MediaItem(),
                    )
                )
            )
        self.assertSequenceEqual(
            (
                "While filtering unknown media item with name 'foo' using "
                'JustWatch filter config:\nlocale: "en_US"\n',
            ),
            error.exception.__notes__,
        )

    def test_extra_human_readable(self) -> None:
        self._mock_api.get.return_value = {
            "offers": [
                _offer(
                    package_short_name="foo",
                    monetization_type="bar",
                    available_to=_TIME_IN_FUTURE_1.isoformat(),
                )
            ]
        }
        test_filter = justwatch.Filter(
            json_format.ParseDict(
                {"locale": "en_US", "anyAvailability": True},
                config_pb2.JustWatchFilter(),
            ),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {"name": "foo", "justwatchId": "movie/1"},
                    config_pb2.MediaItem(),
                )
            )
        )

        self.assertEqual(
            {f"Foo+ (bar, until {_TIME_IN_FUTURE_1})"},
            {extra.human_readable() for extra in result.extra},
        )

    def test_possible_unknown_placeholder_datetime(self) -> None:
        self._mock_api.get.return_value = {
            "offers": [
                _offer(
                    package_short_name="foo",
                    monetization_type="bar",
                    available_from="0042-01-01T00:00:00Z",
                )
            ]
        }
        test_filter = justwatch.Filter(
            json_format.ParseDict(
                {"locale": "en_US", "anyAvailability": True},
                config_pb2.JustWatchFilter(),
            ),
            api=self._mock_api,
        )

        with self.assertWarnsRegex(UserWarning, "0042.*might be a placeholder"):
            result = test_filter.filter(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(
                        {"name": "foo", "justwatchId": "movie/1"},
                        config_pb2.MediaItem(),
                    )
                )
            )
        self.assertEqual(
            media_filter.FilterResult(
                True, extra={_offer_extra("Foo+", ("bar",))}
            ),
            result,
        )


if __name__ == "__main__":
    absltest.main()
