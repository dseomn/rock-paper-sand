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

from collections.abc import Sequence
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
import requests

from rock_paper_sand import wikidata


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


if __name__ == "__main__":
    absltest.main()
