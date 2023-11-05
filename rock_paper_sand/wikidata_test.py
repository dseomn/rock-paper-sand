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

from collections.abc import Collection, Mapping, Sequence, Set
import datetime
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
from rock_paper_sand import wikidata_value
from rock_paper_sand.proto import config_pb2

_PRECISION_YEAR = 9
_PRECISION_MONTH = 10
_PRECISION_DAY = 11

_NOW = datetime.datetime.now(tz=datetime.timezone.utc)
_TIME_FORMAT = "+%Y-%m-%dT%H:%M:%SZ"
_TIME_IN_PAST_2 = (_NOW - datetime.timedelta(days=4)).strftime(_TIME_FORMAT)
_TIME_IN_PAST_1 = (_NOW - datetime.timedelta(days=2)).strftime(_TIME_FORMAT)
_TIME_IN_FUTURE_1 = (_NOW + datetime.timedelta(days=2)).strftime(_TIME_FORMAT)
_TIME_IN_FUTURE_2 = (_NOW + datetime.timedelta(days=4)).strftime(_TIME_FORMAT)


def _snak_item(item_id: str) -> Any:
    return {
        "snaktype": "value",
        "datatype": "wikibase-item",
        "datavalue": {
            "type": "wikibase-entityid",
            "value": {"entity-type": "item", "id": item_id},
        },
    }


def _snak_time(time: str, *, precision: int = _PRECISION_DAY) -> Any:
    return {
        "snaktype": "value",
        "datatype": "time",
        "datavalue": {
            "type": "time",
            "value": {
                "calendarmodel": (
                    wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                ),
                "timezone": 0,
                "before": 0,
                "after": 0,
                "precision": precision,
                "time": time,
            },
        },
    }


def _sparql_item(item_id: str) -> Any:
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{item_id}"}


def _sparql_string(value: str) -> Any:
    return {"type": "literal", "value": value}


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

        first_response = self._api.item(wikidata_value.Item("Q1"))
        second_response = self._api.item(wikidata_value.Item("Q1"))

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

    def test_sparql(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {"bindings": [{"foo": "bar"}]}
        }

        results = self._api.sparql("SELECT ...")

        self.assertEqual([{"foo": "bar"}], results)
        self.assertSequenceEqual(
            (
                mock.call.get(
                    "https://query.wikidata.org/sparql",
                    params=[("query", "SELECT ...")],
                    headers={"Accept": "application/sparql-results+json"},
                ),
                mock.call.get().raise_for_status(),
                mock.call.get().json(),
            ),
            self._mock_session.mock_calls,
        )

    def test_item_classes(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "entities": {
                "Q1": {
                    "claims": {
                        wikidata_value.P_INSTANCE_OF.id: [
                            {"rank": "normal", "mainsnak": _snak_item("Q2")},
                            {"rank": "normal", "mainsnak": _snak_item("Q3")},
                        ],
                    }
                }
            }
        }

        first_result = self._api.item_classes(wikidata_value.Item("Q1"))
        second_result = self._api.item_classes(wikidata_value.Item("Q1"))

        expected_classes = {
            wikidata_value.Item("Q2"),
            wikidata_value.Item("Q3"),
        }
        self.assertEqual(expected_classes, first_result)
        self.assertEqual(expected_classes, second_result)
        # Note that this only happens once because the second time is cached.
        self._mock_session.get.assert_called_once_with(
            "https://www.wikidata.org/wiki/Special:EntityData/Q1.json"
        )

    def test_transitive_subclasses(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {
                "bindings": [
                    {"class": _sparql_item("Q1")},
                    {"class": _sparql_item("Q2")},
                ]
            }
        }

        first_result = self._api.transitive_subclasses(
            wikidata_value.Item("Q1")
        )
        second_result = self._api.transitive_subclasses(
            wikidata_value.Item("Q1")
        )

        expected_subclasses = {
            wikidata_value.Item("Q1"),
            wikidata_value.Item("Q2"),
        }
        self.assertEqual(expected_subclasses, first_result)
        self.assertEqual(expected_subclasses, second_result)
        # Note that this only happens once because the second time is cached.
        self._mock_session.get.assert_called_once()

    @parameterized.named_parameters(
        dict(
            testcase_name="no_results",
            sparql_results=[],
            expected_result=dict(
                parents=(),
                siblings=(),
                children=(),
                loose=(),
            ),
            expected_cached_classes={},
        ),
        dict(
            testcase_name="with_results",
            sparql_results=[
                {
                    "item": _sparql_item("Q2"),
                    "relation": _sparql_string("parent"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q31"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q31"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q32"),
                },
                {
                    "item": _sparql_item("Q4"),
                    "relation": _sparql_string("child"),
                },
                {
                    "item": _sparql_item("Q5"),
                    "relation": _sparql_string("child"),
                },
                {
                    "item": _sparql_item("Q4"),
                    "relation": _sparql_string("loose"),
                },
            ],
            expected_result=dict(
                parents=("Q2",),
                siblings=("Q3",),
                children=("Q4", "Q5"),
                loose=("Q4",),
            ),
            expected_cached_classes={
                "Q2": (),
                "Q3": ("Q31", "Q32"),
                "Q4": (),
                "Q5": (),
            },
        ),
    )
    def test_related_media(
        self,
        *,
        sparql_results: list[Any],
        expected_result: Mapping[str, Collection[str]],
        expected_cached_classes: Mapping[str, Collection[str]],
    ) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {"bindings": sparql_results}
        }

        first_result = self._api.related_media(wikidata_value.Item("Q1"))
        second_result = self._api.related_media(wikidata_value.Item("Q1"))
        actual_classes = {
            item: self._api.item_classes(item)
            for item in {
                *first_result.parents,
                *first_result.siblings,
                *first_result.children,
                *first_result.loose,
            }
        }

        expected_related_media = wikidata.RelatedMedia(
            **{
                key: frozenset(map(wikidata_value.Item, values))
                for key, values in expected_result.items()
            }
        )
        expected_classes = {
            wikidata_value.Item(item_id): frozenset(
                map(wikidata_value.Item, classes)
            )
            for item_id, classes in expected_cached_classes.items()
        }
        self.assertEqual(expected_related_media, first_result)
        self.assertEqual(expected_related_media, second_result)
        self.assertEqual(expected_classes, actual_classes)
        # Note that this only happens once because the second related_media()
        # call and all the item_classes() calls are cached.
        self._mock_session.get.assert_called_once()

    def test_related_media_error(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {
                "bindings": [
                    {
                        "item": _sparql_item("Q2"),
                        "relation": _sparql_string("kumquat"),
                    }
                ]
            }
        }

        with self.assertRaisesRegex(ValueError, "kumquat"):
            self._api.related_media(wikidata_value.Item("Q1"))


class WikidataUtilsTest(parameterized.TestCase):
    # pylint: disable=protected-access
    @parameterized.named_parameters(
        dict(
            testcase_name="preferred",
            item={
                "claims": {
                    "P1": [
                        {"id": "foo", "rank": "preferred"},
                        {"id": "quux", "rank": "normal"},
                        {"id": "baz", "rank": "deprecated"},
                        {"id": "bar", "rank": "preferred"},
                    ],
                },
            },
            prop=wikidata_value.Property("P1"),
            statements=(
                {"id": "foo", "rank": "preferred"},
                {"id": "bar", "rank": "preferred"},
            ),
        ),
        dict(
            testcase_name="normal",
            item={
                "claims": {
                    "P1": [
                        {"id": "foo", "rank": "normal"},
                        {"id": "quux", "rank": "deprecated"},
                        {"id": "bar", "rank": "normal"},
                    ],
                },
            },
            prop=wikidata_value.Property("P1"),
            statements=(
                {"id": "foo", "rank": "normal"},
                {"id": "bar", "rank": "normal"},
            ),
        ),
        dict(
            testcase_name="deprecated",
            item={
                "claims": {
                    "P1": [
                        {"id": "quux", "rank": "deprecated"},
                    ],
                },
            },
            prop=wikidata_value.Property("P1"),
            statements=(),
        ),
        dict(
            testcase_name="empty",
            item={
                "claims": {
                    "P1": [],
                },
            },
            prop=wikidata_value.Property("P1"),
            statements=(),
        ),
        dict(
            testcase_name="missing",
            item={"claims": {}},
            prop=wikidata_value.Property("P1"),
            statements=(),
        ),
    )
    def test_truthy_statements(
        self,
        *,
        item: Any,
        prop: wikidata_value.Property,
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
            testcase_name="datatype_not_item",
            snak={"snaktype": "value", "datatype": "string"},
            error_class=ValueError,
            error_regex=r"non-item",
        ),
        dict(
            testcase_name="type_not_item",
            snak={
                "snaktype": "value",
                "datatype": "wikibase-item",
                "datavalue": {"type": "string"},
            },
            error_class=ValueError,
            error_regex=r"non-item",
        ),
        dict(
            testcase_name="entity_type_not_item",
            snak={
                "snaktype": "value",
                "datatype": "wikibase-item",
                "datavalue": {
                    "type": "wikibase-entityid",
                    "value": {"entity-type": "foo"},
                },
            },
            error_class=ValueError,
            error_regex=r"non-item",
        ),
    )
    def test_parse_snak_item_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata._parse_snak_item(snak)

    def test_parse_snak_item(self) -> None:
        self.assertEqual(
            wikidata_value.Item("Q1"),
            wikidata._parse_snak_item(_snak_item("Q1")),
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
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                        ),
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
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                        ),
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
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                        ),
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
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                        ),
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
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                        ),
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

    @parameterized.named_parameters(
        dict(
            testcase_name="datatype_not_time",
            statement={
                "mainsnak": {"snaktype": "novalue", "datatype": "string"},
            },
            error_class=ValueError,
            error_regex=r"non-time",
        ),
        dict(
            testcase_name="somevalue_with_qualifiers",
            statement={
                "mainsnak": {"snaktype": "somevalue", "datatype": "time"},
                "qualifiers": {"P1": []},
            },
            error_class=NotImplementedError,
            error_regex=r"somevalue time with qualifiers",
        ),
        dict(
            testcase_name="invalid_snaktype",
            statement={
                "mainsnak": {"snaktype": "foo", "datatype": "time"},
            },
            error_class=ValueError,
            error_regex=r"Unexpected snaktype",
        ),
    )
    def test_parse_statement_time_error(
        self,
        *,
        statement: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata._parse_statement_time(statement)

    @parameterized.parameters(
        (
            {
                "mainsnak": _snak_time(
                    "+2000-01-01T00:00:00Z", precision=_PRECISION_DAY
                )
            },
            ("2000-01-01T00:00:00+00:00", "2000-01-01T23:59:59.999999+00:00"),
        ),
        (
            {"mainsnak": {"snaktype": "somevalue", "datatype": "time"}},
            (None, None),
        ),
        (
            {"mainsnak": {"snaktype": "novalue", "datatype": "time"}},
            (None, None),
        ),
    )
    def test_parse_statement_time(
        self,
        statement: Any,
        values: tuple[str | None, str | None],
    ) -> None:
        self.assertSequenceEqual(
            values,
            tuple(
                (None if value is None else value.isoformat())
                for value in wikidata._parse_statement_time(statement)
            ),
        )

    def test_parse_sparql_result_item_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-uri"):
            wikidata._parse_sparql_result_item({"type": "literal"})

    def test_parse_sparql_result_item(self) -> None:
        self.assertEqual(
            wikidata_value.Item("Q1"),
            wikidata._parse_sparql_result_item(_sparql_item("Q1")),
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="not_literal",
            term={"type": "uri"},
            error_regex=r"non-literal",
        ),
        dict(
            testcase_name="not_plain",
            term={
                "type": "literal",
                "value": "Alice",
                "datatype": "https://example.com/person",
            },
            error_regex=r"non-plain",
        ),
    )
    def test_parse_sparql_result_string_error(
        self,
        *,
        term: Any,
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(ValueError, error_regex):
            wikidata._parse_sparql_result_string(term)

    def test_parse_sparql_result_string(self) -> None:
        self.assertEqual(
            "foo",
            wikidata._parse_sparql_result_string(_sparql_string("foo")),
        )


class WikidataFilterTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_api = mock.create_autospec(
            wikidata.Api, spec_set=True, instance=True
        )
        self._mock_api.transitive_subclasses.side_effect = lambda class_id: {
            class_id
        }

    @parameterized.named_parameters(
        dict(
            testcase_name="no_item_id",
            filter_config={},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={"Q1": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_no_match",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={"Q1": {"claims": {}}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="release_statuses_unknown",
            filter_config={"releaseStatuses": ["RELEASE_STATUS_UNSPECIFIED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={"Q1": {"claims": {}}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_range",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_2),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_start",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_in_range",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_start",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_end",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_range",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_2),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_end",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_release",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_PUBLICATION_DATE.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_release",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_items={
                "Q1": {
                    "claims": {
                        wikidata_value.P_PUBLICATION_DATE.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="related_media_ignores_non_top_level",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            parent_fully_qualified_name="foo",
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="related_media_none",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="related_media_not_loose",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q4"}],
            },
            api_item_classes={
                "Q1": set(),
                "Q2": set(),
                "Q3": set(),
                "Q4": set(),
                "Q5": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.Item("Q2"),
                        wikidata_value.Item("Q3"),
                    },
                    loose=set(),
                ),
                "Q2": wikidata.RelatedMedia(
                    parents={wikidata_value.Item("Q1")},
                    siblings={wikidata_value.Item("Q3")},
                    children=set(),
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents={wikidata_value.Item("Q1")},
                    siblings={
                        wikidata_value.Item("Q2"),
                        wikidata_value.Item("Q4"),
                    },
                    children=set(),
                    loose=set(),
                ),
                "Q4": wikidata.RelatedMedia(
                    parents={wikidata_value.Item("Q5")},
                    siblings={wikidata_value.Item("Q3")},
                    children=set(),
                    loose=set(),
                ),
                "Q5": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.Item("Q4")},
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q2"
                    ),
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q3"
                    ),
                    # Q4 is in the config, so not shown here.
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q5"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_loose",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q2"}],
            },
            api_item_classes={
                "Q2": set(),
                "Q3": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    # Q2 is upgraded to non-loose, because it's also in the
                    # config.
                    loose={wikidata_value.Item("Q2")},
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose={wikidata_value.Item("Q3")},
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "loosely-related item: https://www.wikidata.org/wiki/Q3"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_config_has_unrelated",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q2"}],
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "item in config file that's not related to "
                        "https://www.wikidata.org/wiki/Q1: "
                        "https://www.wikidata.org/wiki/Q2"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_ignores_generic_items",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings={wikidata_value.Q_PARATEXT},
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="related_media_ignores_integral_children",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_item_classes={
                "Q1": set(),
                "Q2": {wikidata_value.Q_TELEVISION_SERIES},
                "Q21": {wikidata_value.Q_TELEVISION_SERIES_EPISODE},
                "Q22": {
                    wikidata_value.Q_TELEVISION_SERIES_EPISODE,
                    wikidata_value.Q_TELEVISION_SPECIAL,
                },
                "Q23": {wikidata_value.Q_TELEVISION_SERIES_SEASON},
                "Q31": {wikidata_value.Q_LITERARY_WORK},
                "Q3": {wikidata_value.Q_LITERARY_WORK},
                "Q4": {wikidata_value.Q_FILM},
                "Q41": {wikidata_value.Q_RELEASE_GROUP},
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.Item("Q2"),
                        wikidata_value.Item("Q31"),
                        wikidata_value.Item("Q4"),
                    },
                    loose=set(),
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.Item("Q21"),
                        wikidata_value.Item("Q22"),
                        wikidata_value.Item("Q23"),
                    },
                    loose=set(),
                ),
                "Q21": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q22": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q23": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q31": wikidata.RelatedMedia(
                    parents={wikidata_value.Item("Q3")},
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q4": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.Item("Q41")},
                    loose=set(),
                ),
                "Q41": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q2"
                    ),
                    # Q21 is an integral child of Q2.
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q22"
                    ),
                    # Q23 is an integral child of Q2.
                    # Q31 is an integral child of Q3.
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q3"
                    ),
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q4"
                    ),
                    # Q41 is an integral child of Q4.
                },
            ),
        ),
        dict(
            testcase_name="related_media_does_not_traverse_collections",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_item_classes={
                "Q1": set(),
                "Q2": {wikidata_value.Q_LIST},
                "Q3": {wikidata_value.Q_ANTHOLOGY},
                "Q4": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents={wikidata_value.Item("Q2")},
                    siblings=set(),
                    children={wikidata_value.Item("Q3")},
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.Item("Q4")},
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: https://www.wikidata.org/wiki/Q3"
                    ),
                },
            ),
        ),
    )
    def test_filter(
        self,
        *,
        filter_config: Any,
        item: Any,
        parent_fully_qualified_name: str | None = None,
        api_items: Mapping[str, Any] = immutabledict.immutabledict(),
        api_item_classes: Mapping[str, Set[wikidata_value.Item]] = (
            immutabledict.immutabledict()
        ),
        api_related_media: Mapping[str, wikidata.RelatedMedia] = (
            immutabledict.immutabledict()
        ),
        expected_result: media_filter.FilterResult,
    ) -> None:
        self._mock_api.item.side_effect = lambda item_id: api_items[item_id.id]
        self._mock_api.item_classes.side_effect = (
            lambda item_id: api_item_classes[item_id.id]
        )
        self._mock_api.related_media.side_effect = (
            lambda item_id: api_related_media[item_id.id]
        )
        test_filter = wikidata.Filter(
            json_format.ParseDict(filter_config, config_pb2.WikidataFilter()),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_filter.FilterRequest(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(item, config_pb2.MediaItem()),
                    parent_fully_qualified_name=parent_fully_qualified_name,
                )
            )
        )

        self.assertEqual(expected_result, result)

    def test_too_many_related_items(self) -> None:
        self._mock_api.item_classes.return_value = set()
        self._mock_api.related_media.return_value = wikidata.RelatedMedia(
            parents=set(),
            siblings={wikidata_value.Item(f"Q{n}") for n in range(1001)},
            children=set(),
            loose=set(),
        )
        test_filter = wikidata.Filter(
            json_format.ParseDict(
                {"relatedMedia": {}}, config_pb2.WikidataFilter()
            ),
            api=self._mock_api,
        )
        request = media_filter.FilterRequest(
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {"name": "foo", "wikidata": "Q99999"},
                    config_pb2.MediaItem(),
                )
            )
        )

        with self.assertRaisesRegex(ValueError, "Too many related media items"):
            test_filter.filter(request)


if __name__ == "__main__":
    absltest.main()
