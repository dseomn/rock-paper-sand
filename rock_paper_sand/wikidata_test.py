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

from collections.abc import Mapping, Sequence
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict
import requests

from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand import wikidata
from rock_paper_sand.proto import config_pb2

_PROLEPTIC_GREGORIAN = "http://www.wikidata.org/entity/Q1985727"
_PRECISION_YEAR = 9
_PRECISION_MONTH = 10
_PRECISION_DAY = 11


def _snak_time(time: str, *, precision: int = _PRECISION_DAY) -> Any:
    return {
        "snaktype": "value",
        "datatype": "time",
        "datavalue": {
            "type": "time",
            "value": {
                "calendarmodel": _PROLEPTIC_GREGORIAN,
                "timezone": 0,
                "before": 0,
                "after": 0,
                "precision": precision,
                "time": time,
            },
        },
    }


class WikidataSessionTest(parameterized.TestCase):
    def test_session(self) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        with wikidata.requests_session() as session:
            self.assertIsInstance(session, requests.Session)


class WikidataApiTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_session = mock.create_autospec(
            requests.Session, spec_set=True, instance=True
        )
        self._api = wikidata.Api(session=self._mock_session)

    def test_item(self) -> None:
        item = {"foo": "bar"}
        self._mock_session.get.return_value.json.return_value = {
            "entities": {"Q1": item}
        }

        first_response = self._api.item("Q1")
        second_response = self._api.item("Q1")

        self.assertEqual(item, first_response)
        self.assertEqual(item, second_response)
        self.assertSequenceEqual(
            (
                # Note that this only happens once because the second time is
                # cached.
                mock.call.get(
                    "https://www.wikidata.org/wiki/Special:EntityData/Q1.json"
                ),
                mock.call.get().raise_for_status(),
                mock.call.get().json(),
            ),
            self._mock_session.mock_calls,
        )


class WikidataUtilsTest(parameterized.TestCase):
    # pylint: disable=protected-access
    @parameterized.named_parameters(
        dict(
            testcase_name="preferred",
            item={
                "claims": {
                    "P577": [
                        {"id": "foo", "rank": "preferred"},
                        {"id": "quux", "rank": "normal"},
                        {"id": "baz", "rank": "deprecated"},
                        {"id": "bar", "rank": "preferred"},
                    ],
                },
            },
            prop=wikidata._Property.PUBLICATION_DATE,
            statements=(
                {"id": "foo", "rank": "preferred"},
                {"id": "bar", "rank": "preferred"},
            ),
        ),
        dict(
            testcase_name="normal",
            item={
                "claims": {
                    "P577": [
                        {"id": "foo", "rank": "normal"},
                        {"id": "quux", "rank": "deprecated"},
                        {"id": "bar", "rank": "normal"},
                    ],
                },
            },
            prop=wikidata._Property.PUBLICATION_DATE,
            statements=(
                {"id": "foo", "rank": "normal"},
                {"id": "bar", "rank": "normal"},
            ),
        ),
        dict(
            testcase_name="deprecated",
            item={
                "claims": {
                    "P577": [
                        {"id": "quux", "rank": "deprecated"},
                    ],
                },
            },
            prop=wikidata._Property.PUBLICATION_DATE,
            statements=(),
        ),
        dict(
            testcase_name="empty",
            item={
                "claims": {
                    "P577": [],
                },
            },
            prop=wikidata._Property.PUBLICATION_DATE,
            statements=(),
        ),
        dict(
            testcase_name="missing",
            item={"claims": {}},
            prop=wikidata._Property.PUBLICATION_DATE,
            statements=(),
        ),
    )
    def test_truthy_statements(
        self,
        *,
        item: Any,
        prop: wikidata._Property,
        statements: Sequence[Any],
    ) -> None:
        self.assertSequenceEqual(
            statements, wikidata._truthy_statements(item, prop)
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="not_value",
            snak={"snaktype": "somevalue"},
            error_class=NotImplementedError,
            error_regex=r"non-value",
        ),
        dict(
            testcase_name="datatype_not_time",
            snak={"snaktype": "value", "datatype": "string"},
            error_class=ValueError,
            error_regex=r"non-time",
        ),
        dict(
            testcase_name="type_not_time",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {"type": "string"},
            },
            error_class=ValueError,
            error_regex=r"non-time",
        ),
        dict(
            testcase_name="not_gregorian",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": "http://www.wikidata.org/entity/Q1",
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"non-Gregorian",
        ),
        dict(
            testcase_name="not_utc",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": _PROLEPTIC_GREGORIAN,
                        "timezone": 42,
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"non-UTC",
        ),
        dict(
            testcase_name="before",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": _PROLEPTIC_GREGORIAN,
                        "timezone": 0,
                        "before": 42,
                        "after": 0,
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"uncertainty range",
        ),
        dict(
            testcase_name="after",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": _PROLEPTIC_GREGORIAN,
                        "timezone": 0,
                        "before": 0,
                        "after": 42,
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"uncertainty range",
        ),
        dict(
            testcase_name="unimplemented_precision",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": _PROLEPTIC_GREGORIAN,
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 0,
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"precision",
        ),
        dict(
            testcase_name="no_match",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": _PROLEPTIC_GREGORIAN,
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 11,
                        "time": "foo",
                    },
                },
            },
            error_class=ValueError,
            error_regex=r"Cannot parse time",
        ),
    )
    def test_parse_snak_time_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata._parse_snak_time(snak)

    @parameterized.parameters(
        (
            _snak_time("+1979-10-12T00:00:00Z", precision=_PRECISION_DAY),
            ("1979-10-12T00:00:00+00:00", "1979-10-12T23:59:59.999999+00:00"),
        ),
        (
            # day is 00
            _snak_time("+2008-07-00T00:00:00Z", precision=_PRECISION_MONTH),
            ("2008-07-01T00:00:00+00:00", "2008-07-31T23:59:59.999999+00:00"),
        ),
        (
            _snak_time("+1938-01-01T00:00:00Z", precision=_PRECISION_YEAR),
            ("1938-01-01T00:00:00+00:00", "1938-12-31T23:59:59.999999+00:00"),
        ),
        (
            # month and day are 00
            _snak_time("+1600-00-00T00:00:00Z", precision=_PRECISION_YEAR),
            ("1600-01-01T00:00:00+00:00", "1600-12-31T23:59:59.999999+00:00"),
        ),
    )
    def test_parse_snak_time(
        self,
        snak: Any,
        values: tuple[str, str],
    ) -> None:
        self.assertSequenceEqual(
            values,
            tuple(
                value.isoformat() for value in wikidata._parse_snak_time(snak)
            ),
        )


class WikidataFilterTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_api = mock.create_autospec(
            wikidata.Api, spec_set=True, instance=True
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="no_qid",
            filter_config={},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={},
            item={"name": "foo", "wikidata": "Q1"},
            api_data={"Q1": {}},
            expected_result=media_filter.FilterResult(True),
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
        self._mock_api.item.side_effect = lambda qid: api_data[qid]
        test_filter = wikidata.Filter(
            json_format.ParseDict(filter_config, config_pb2.WikidataFilter()),
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


if __name__ == "__main__":
    absltest.main()
