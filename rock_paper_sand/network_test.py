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
import requests.adapters
import requests.exceptions
import requests_cache

from rock_paper_sand import network


class NetworkTest(parameterized.TestCase):
    def test_requests_cache_defaults(self) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        with requests_cache.CachedSession(**network.requests_cache_defaults()):
            pass

    def test_requests_http_adapter(self) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        self.assertIsInstance(
            network.requests_http_adapter(), requests.adapters.HTTPAdapter
        )

    def test_configure_session(self) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        with requests.session() as session:
            network.configure_session(session)
            self.assertIn("User-Agent", session.headers)

    @parameterized.parameters(
        "http://example.com",
        "https://example.com",
    )
    def test_null_requests_session(self, url: str) -> None:
        session = network.null_requests_session()
        with self.assertRaises(requests.exceptions.InvalidSchema):
            session.get(url)


if __name__ == "__main__":
    absltest.main()
