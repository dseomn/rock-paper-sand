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

from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
import requests

from rock_paper_sand import justwatch


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


if __name__ == "__main__":
    absltest.main()
