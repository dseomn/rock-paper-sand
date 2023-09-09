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

import argparse
import io
import textwrap
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import justwatch
from rock_paper_sand import justwatch_subcommand


class JustWatchSubcommandTest(parameterized.TestCase):
    def setUp(self):
        super().setUp()
        self._mock_api = mock.create_autospec(
            justwatch.Api, instance=True, spec_set=True
        )

    def test_search(self):
        parser = argparse.ArgumentParser()
        output = io.StringIO()
        self._mock_api.post.return_value = {
            "items": [
                {
                    "object_type": "movie",
                    "id": 42,
                    "full_path": "/movie-1234",
                    "title": "They had movies in 1234?",
                    "original_release_year": 1234,
                },
                {
                    "object_type": "movie",
                    "id": 17,
                    "full_path": "/movie-no-year",
                    "title": "When did this come out?",
                },
                {
                    "object_type": "show",
                    "id": 5,
                    "full_path": "/this-is-a-show",
                    "title": "This is a Show",
                    "original_release_year": 2002,
                },
            ],
        }

        command = justwatch_subcommand.Search(parser)
        command.run(
            parser.parse_args(["--locale=en_US", "foo bar", "quux"]),
            out_file=output,
            api=self._mock_api,
        )

        self.assertSequenceEqual(
            (
                mock.call.post(
                    "titles/en_US/popular",
                    {"query": "foo bar quux"},
                ),
            ),
            self._mock_api.mock_calls,
        )
        self.assertEqual(
            textwrap.dedent(
                """\
                - name: "They had movies in 1234? (1234)"
                  justwatchId: movie/42  # https://www.justwatch.com/movie-1234
                - name: "When did this come out? (?)"
                  justwatchId: movie/17  # https://www.justwatch.com/movie-no-year
                - name: "This is a Show (2002 - ?)"
                  justwatchId: show/5  # https://www.justwatch.com/this-is-a-show
                """
            ),
            output.getvalue(),
        )


if __name__ == "__main__":
    absltest.main()
