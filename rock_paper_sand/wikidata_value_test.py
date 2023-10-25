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

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import wikidata_value


class WikidataValueTest(parameterized.TestCase):
    def test_invalid_item_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.Item("foo")

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
    def test_invalid_item_string(self, value: str) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.Item.from_string(value)

    @parameterized.parameters(
        ("Q1", "Q1"),
        ("https://www.wikidata.org/wiki/Q1", "Q1"),
    )
    def test_valid_item_string(self, value: str, expected_id: str) -> None:
        self.assertEqual(expected_id, wikidata_value.Item.from_string(value).id)

    def test_item_uri(self) -> None:
        self.assertEqual(
            "http://www.wikidata.org/entity/Q1",
            wikidata_value.Item("Q1").uri,
        )

    def test_item_from_uri_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.Item.from_uri("Q1")

    def test_item_from_uri_valid(self) -> None:
        self.assertEqual(
            "Q1",
            wikidata_value.Item.from_uri(
                "http://www.wikidata.org/entity/Q1"
            ).id,
        )

    def test_invalid_property_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata IRI or ID"):
            wikidata_value.Property("foo")

    @parameterized.parameters(
        ("P6", "P6"),
        ("https://www.wikidata.org/wiki/Property:P6", "P6"),
    )
    def test_valid_property_string(self, value: str, expected_id: str) -> None:
        self.assertEqual(
            expected_id, wikidata_value.Property.from_string(value).id
        )


if __name__ == "__main__":
    absltest.main()
