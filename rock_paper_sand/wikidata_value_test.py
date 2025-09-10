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

from collections.abc import Callable, Collection, Mapping, Sequence
import datetime
from typing import Any

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import wikidata_value

_PRECISION_YEAR = 9
_PRECISION_MONTH = 10
_PRECISION_DAY = 11


def _snak_time(
    time: str,
    *,
    calendarmodel: str = wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri,
    before: int = 0,
    after: int = 0,
    precision: int = _PRECISION_DAY,
) -> Any:
    return {
        "snaktype": "value",
        "datatype": "time",
        "datavalue": {
            "type": "time",
            "value": {
                "calendarmodel": calendarmodel,
                "timezone": 0,
                "before": before,
                "after": after,
                "precision": precision,
                "time": time,
            },
        },
    }


class WikidataValueTest(parameterized.TestCase):
    @parameterized.parameters(
        wikidata_value.ItemRef, wikidata_value.PropertyRef
    )
    def test_invalid_entity_id(
        self, ref_cls: type[wikidata_value.EntityRef]
    ) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            ref_cls("foo")

    @parameterized.parameters(
        (wikidata_value.ItemRef("Q1"), "https://www.wikidata.org/wiki/Q1"),
        (
            wikidata_value.PropertyRef("P1"),
            "https://www.wikidata.org/wiki/Property:P1",
        ),
    )
    def test_entity_ref_string(
        self, entity_ref: wikidata_value.EntityRef, expected_string: str
    ) -> None:
        self.assertEqual(expected_string, str(entity_ref))

    @parameterized.parameters(
        "foo",
        "Q",
        "Q💯",
        "Q-1",
        "Q1.2",
        "Q1foo",
        "q1",
        "https://example.com/Q1",
        "https://www.wikidata.org/wiki/foo",
        "https://www.wikidata.org/wiki/Q",
        "https://www.wikidata.org/wiki/Q1foo",
    )
    def test_entity_ref_from_string_invalid(self, value: str) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.ItemRef.from_string(value)

    @parameterized.parameters(
        (wikidata_value.ItemRef, "Q1", "Q1"),
        (wikidata_value.ItemRef, "https://www.wikidata.org/wiki/Q1", "Q1"),
        (wikidata_value.PropertyRef, "P6", "P6"),
        (
            wikidata_value.PropertyRef,
            "https://www.wikidata.org/wiki/Property:P6",
            "P6",
        ),
    )
    def test_entity_ref_from_string_valid(
        self,
        ref_cls: type[wikidata_value.EntityRef],
        value: str,
        expected_id: str,
    ) -> None:
        self.assertEqual(expected_id, ref_cls.from_string(value).id)

    def test_entity_ref_uri(self) -> None:
        self.assertEqual(
            "http://www.wikidata.org/entity/Q1",
            wikidata_value.ItemRef("Q1").uri,
        )

    def test_entity_ref_from_uri_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.ItemRef.from_uri("Q1")

    def test_entity_ref_from_uri_valid(self) -> None:
        self.assertEqual(
            "Q1",
            wikidata_value.ItemRef.from_uri(
                "http://www.wikidata.org/entity/Q1"
            ).id,
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
    def test_snak_item_value_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata_value.Snak(json=snak).item_value()

    def test_snak_item_value(self) -> None:
        self.assertEqual(
            wikidata_value.ItemRef("Q1"),
            wikidata_value.Snak(
                json={
                    "snaktype": "value",
                    "datatype": "wikibase-item",
                    "datavalue": {
                        "type": "wikibase-entityid",
                        "value": {"entity-type": "item", "id": "Q1"},
                    },
                }
            ).item_value(),
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="not_value",
            snak={"snaktype": "somevalue"},
            error_class=NotImplementedError,
            error_regex=r"non-value",
        ),
        dict(
            testcase_name="datatype_not_string",
            snak={"snaktype": "value", "datatype": "wikibase-item"},
            error_class=ValueError,
            error_regex=r"non-string",
        ),
        dict(
            testcase_name="type_not_string",
            snak={
                "snaktype": "value",
                "datatype": "string",
                "datavalue": {"type": "wikibase-entityid"},
            },
            error_class=ValueError,
            error_regex=r"non-string",
        ),
    )
    def test_snak_string_value_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata_value.Snak(json=snak).string_value()

    def test_snak_string_value(self) -> None:
        self.assertEqual(
            "foo",
            wikidata_value.Snak(
                json={
                    "snaktype": "value",
                    "datatype": "string",
                    "datavalue": {"type": "string", "value": "foo"},
                }
            ).string_value(),
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
        dict(
            testcase_name="recent_julian",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": (
                            wikidata_value.Q_PROLEPTIC_JULIAN_CALENDAR.uri
                        ),
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 11,
                        "time": "+2000-01-01T00:00:00Z",
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"recent Julian",
        ),
        dict(
            testcase_name="unknown_calendar_model",
            snak={
                "snaktype": "value",
                "datatype": "time",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "calendarmodel": "http://www.wikidata.org/entity/Q1",
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 11,
                        "time": "+1979-10-12T00:00:00Z",
                    },
                },
            },
            error_class=NotImplementedError,
            error_regex=r"calendar model",
        ),
    )
    def test_snak_time_value_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata_value.Snak(json=snak).time_value()

    @parameterized.parameters(
        (
            _snak_time(
                "+0100-01-01T00:00:00Z",
                calendarmodel=wikidata_value.Q_PROLEPTIC_JULIAN_CALENDAR.uri,
            ),
            (
                wikidata_value.PseudoDatetime.PAST,
                wikidata_value.PseudoDatetime.PAST,
            ),
        ),
        (
            _snak_time("+1979-10-12T00:00:00Z", precision=_PRECISION_DAY),
            ("1979-10-12T00:00:00+00:00", "1979-10-12T23:59:59.999999+00:00"),
        ),
        (
            _snak_time(
                "+1979-10-12T00:00:00Z",
                before=1,
                after=2,
                precision=_PRECISION_DAY,
            ),
            ("1979-10-11T00:00:00+00:00", "1979-10-14T23:59:59.999999+00:00"),
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
    def test_snak_time_value(
        self,
        snak: Any,
        values: tuple[
            str | wikidata_value.PseudoDatetime,
            str | wikidata_value.PseudoDatetime,
        ],
    ) -> None:
        self.assertSequenceEqual(
            values,
            tuple(
                (
                    value.isoformat()
                    if isinstance(value, datetime.datetime)
                    else value
                )
                for value in wikidata_value.Snak(json=snak).time_value()
            ),
        )

    def test_statement_mainsnak(self) -> None:
        mainsnak = {"foo": "bar"}
        self.assertEqual(
            wikidata_value.Snak(json=mainsnak),
            wikidata_value.Statement(json={"mainsnak": mainsnak}).mainsnak(),
        )

    @parameterized.parameters(
        ({}, "P1", ()),
        ({"qualifiers": {}}, "P1", ()),
        ({"qualifiers": {"P1": []}}, "P1", ()),
        (
            {"qualifiers": {"P1": [{"foo": 1}, {"foo": 2}]}},
            "P1",
            ({"foo": 1}, {"foo": 2}),
        ),
    )
    def test_statement_qualifiers(
        self,
        statement: Any,
        property_id: str,
        expected_qualifiers: Collection[Any],
    ) -> None:
        self.assertCountEqual(
            tuple(
                wikidata_value.Snak(json=snak) for snak in expected_qualifiers
            ),
            wikidata_value.Statement(json=statement).qualifiers(
                wikidata_value.PropertyRef(property_id)
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
            testcase_name="somevalue_with_unsupported_qualifiers",
            statement={
                "mainsnak": {"snaktype": "somevalue", "datatype": "time"},
                "qualifiers": {"P1": []},
            },
            error_class=NotImplementedError,
            error_regex=r"somevalue time with unsupported qualifiers",
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
    def test_statement_time_error(
        self,
        *,
        statement: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata_value.Statement(json=statement).time_value()

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
            {
                "mainsnak": {"snaktype": "somevalue", "datatype": "time"},
                "qualifiers": {wikidata_value.P_PLACE_OF_PUBLICATION.id: []},
            },
            (None, None),
        ),
        (
            {"mainsnak": {"snaktype": "novalue", "datatype": "time"}},
            (None, None),
        ),
    )
    def test_statement_time(
        self,
        statement: Any,
        values: tuple[str | None, str | None],
    ) -> None:
        self.assertSequenceEqual(
            values,
            tuple(
                (
                    value.isoformat()
                    if isinstance(value, datetime.datetime)
                    else value
                )
                for value in wikidata_value.Statement(
                    json=statement
                ).time_value()
            ),
        )

    @parameterized.product(
        (
            dict(function=wikidata_value.Entity.label, section="labels"),
            dict(
                function=wikidata_value.Entity.description,
                section="descriptions",
            ),
        ),
        (
            dict(
                mapping={},
                languages=("en",),
                expected_value=None,
            ),
            dict(
                mapping={"en": {"value": "foo"}},
                languages=(),
                expected_value=None,
            ),
            dict(
                mapping={
                    "en": {"value": "foo"},
                    "en-us": {"value": "bar"},
                },
                languages=("qa", "en"),
                expected_value="foo",
            ),
            dict(
                mapping={"en-us": {"value": "foo"}},
                languages=("en",),
                expected_value="foo",
            ),
        ),
    )
    def test_language_keyed_string(
        self,
        *,
        function: Callable[[wikidata_value.Entity, Sequence[str]], str | None],
        section: str,
        mapping: Mapping[str, Any],
        languages: Sequence[str],
        expected_value: str | None,
    ) -> None:
        self.assertEqual(
            expected_value,
            function(
                wikidata_value.Entity(json_full={section: mapping}),
                languages,
            ),
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="preferred",
            entity={
                "claims": {
                    "P1": [
                        {"id": "foo", "rank": "preferred"},
                        {"id": "quux", "rank": "normal"},
                        {"id": "baz", "rank": "deprecated"},
                        {"id": "bar", "rank": "preferred"},
                    ],
                },
            },
            prop=wikidata_value.PropertyRef("P1"),
            statements=(
                {"id": "foo", "rank": "preferred"},
                {"id": "bar", "rank": "preferred"},
            ),
        ),
        dict(
            testcase_name="normal",
            entity={
                "claims": {
                    "P1": [
                        {"id": "foo", "rank": "normal"},
                        {"id": "quux", "rank": "deprecated"},
                        {"id": "bar", "rank": "normal"},
                    ],
                },
            },
            prop=wikidata_value.PropertyRef("P1"),
            statements=(
                {"id": "foo", "rank": "normal"},
                {"id": "bar", "rank": "normal"},
            ),
        ),
        dict(
            testcase_name="deprecated",
            entity={
                "claims": {
                    "P1": [
                        {"id": "quux", "rank": "deprecated"},
                    ],
                },
            },
            prop=wikidata_value.PropertyRef("P1"),
            statements=(),
        ),
        dict(
            testcase_name="empty",
            entity={
                "claims": {
                    "P1": [],
                },
            },
            prop=wikidata_value.PropertyRef("P1"),
            statements=(),
        ),
        dict(
            testcase_name="missing",
            entity={"claims": {}},
            prop=wikidata_value.PropertyRef("P1"),
            statements=(),
        ),
    )
    def test_truthy_statements(
        self,
        *,
        entity: Any,
        prop: wikidata_value.PropertyRef,
        statements: Sequence[Any],
    ) -> None:
        self.assertCountEqual(
            tuple(
                wikidata_value.Statement(json=statement)
                for statement in statements
            ),
            wikidata_value.Entity(json_full=entity).truthy_statements(prop),
        )

    def test_parse_sparql_term_item_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-uri"):
            wikidata_value.parse_sparql_term_item({"type": "literal"})

    def test_parse_sparql_term_item(self) -> None:
        self.assertEqual(
            wikidata_value.ItemRef("Q1"),
            wikidata_value.parse_sparql_term_item(
                {"type": "uri", "value": "http://www.wikidata.org/entity/Q1"}
            ),
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
    def test_parse_sparql_term_string_error(
        self,
        *,
        term: wikidata_value.SparqlTerm,
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(ValueError, error_regex):
            wikidata_value.parse_sparql_term_string(term)

    def test_parse_sparql_term_string(self) -> None:
        self.assertEqual(
            "foo",
            wikidata_value.parse_sparql_term_string(
                {"type": "literal", "value": "foo"}
            ),
        )


if __name__ == "__main__":
    absltest.main()
