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

from collections.abc import Mapping
import datetime
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict
import requests

from rock_paper_sand import config_pb2
from rock_paper_sand import justwatch
from rock_paper_sand import media_filter

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


class JustWatchApiTest(parameterized.TestCase):
    def setUp(self):
        self._mock_session = mock.create_autospec(
            requests.Session, spec_set=True, instance=True
        )
        self._base_url = "http://localhost"
        self._api = justwatch.Api(
            session=self._mock_session, base_url=self._base_url
        )

    def test_get(self):
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

    def test_cache(self):
        self._mock_session.get.return_value.json.return_value = "foo"
        self._api.get("bar")
        self._mock_session.reset_mock()

        data = self._api.get("bar")

        self.assertEqual("foo", data)
        self.assertEmpty(self._mock_session.mock_calls)


class FilterTest(parameterized.TestCase):
    def setUp(self):
        self._mock_api = mock.create_autospec(
            justwatch.Api, spec_set=True, instance=True
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="no_id",
            filter_config={"locale": "en_US"},
            media_item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={"locale": "en_US"},
            media_item={"name": "foo", "justwatchId": "movie/1"},
            api_data={"titles/movie/1/locale/en_US": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="any_availability_no_match",
            filter_config={"locale": "en_US", "anyAvailability": True},
            media_item={"name": "foo", "justwatchId": "movie/1"},
            api_data={"titles/movie/1/locale/en_US": {}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="any_availability_matches",
            filter_config={"locale": "en_US", "anyAvailability": True},
            media_item={"name": "foo", "justwatchId": "movie/1"},
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
                    "foo (bar)",
                    (
                        f"quux (baz, starting {_TIME_IN_FUTURE_1}, until "
                        f"{_TIME_IN_FUTURE_2})"
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
            media_item={"name": "foo", "justwatchId": "movie/1"},
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
                True, extra={"foo (bar)"}
            ),
        ),
    )
    def test_filter(
        self,
        *,
        filter_config: ...,
        media_item: ...,
        api_data: Mapping[str, Any] = immutabledict.immutabledict(),
        expected_result: media_filter.FilterResult,
    ):
        self._mock_api.get.side_effect = lambda relative_url: api_data[
            relative_url
        ]
        test_filter = justwatch.Filter(
            json_format.ParseDict(filter_config, config_pb2.JustWatchFilter()),
            api=self._mock_api,
        )

        result = test_filter.filter(
            json_format.ParseDict(media_item, config_pb2.MediaItem())
        )

        self.assertEqual(expected_result, result)

    def test_possible_unknown_placeholder_datetime(self):
        self._mock_api.get.return_value = {
            "offers": [
                _offer(
                    package_short_name="foo",
                    monetization_type="bar",
                    available_from="1970-01-01T00:00:00Z",
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

        with self.assertWarnsRegex(UserWarning, "1970.*might be a placeholder"):
            result = test_filter.filter(
                json_format.ParseDict(
                    {"name": "foo", "justwatchId": "movie/1"},
                    config_pb2.MediaItem(),
                )
            )
        self.assertEqual(
            media_filter.FilterResult(True, extra={"foo (bar)"}), result
        )


if __name__ == "__main__":
    absltest.main()
