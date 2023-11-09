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

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import wikidata_value


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
    def test_parse_snak_item_error(
        self,
        *,
        snak: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            wikidata_value.parse_snak_item(wikidata_value.Snak(snak))

    def test_parse_snak_item(self) -> None:
        self.assertEqual(
            wikidata_value.ItemRef("Q1"),
            wikidata_value.parse_snak_item(
                wikidata_value.Snak(
                    {
                        "snaktype": "value",
                        "datatype": "wikibase-item",
                        "datavalue": {
                            "type": "wikibase-entityid",
                            "value": {"entity-type": "item", "id": "Q1"},
                        },
                    }
                )
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
        self.assertSequenceEqual(
            statements,
            wikidata_value.Entity(json_full=entity).truthy_statements(prop),
        )


if __name__ == "__main__":
    absltest.main()
