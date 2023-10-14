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

# TODO(https://github.com/python/mypy/issues/8766): Remove this disable.
# mypy: warn-unreachable=false

from collections.abc import Sequence
import json
import pathlib
import textwrap
from typing import Any

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized

from rock_paper_sand import config
from rock_paper_sand import flags_and_constants
from rock_paper_sand import network


class ConfigTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="filter_missing_name",
            config_data={
                "filters": [{}],
            },
            error_regex="name field is required",
            error_notes=("In filters[0] with name ''.",),
        ),
        dict(
            testcase_name="report_missing_name",
            config_data={
                "reports": [{}],
            },
            error_regex="name field is required",
            error_notes=("In reports[0] with name ''.",),
        ),
        dict(
            testcase_name="report_duplicate_name",
            config_data={
                "reports": [
                    {"name": "foo"},
                    {"name": "foo"},
                ],
            },
            error_regex="name field must be unique",
            error_notes=("In reports[1] with name 'foo'.",),
        ),
    )
    def test_invalid_config(
        self,
        *,
        config_data: Any,
        error_regex: str,
        error_notes: Sequence[str],
    ) -> None:
        self.enter_context(
            flagsaver.flagsaver(
                (
                    flags_and_constants.CONFIG_FILE,
                    self.create_tempfile(
                        content=json.dumps(config_data)
                    ).full_path,
                )
            )
        )
        with self.assertRaisesRegex(ValueError, error_regex) as error:
            config.Config.from_config_file(
                justwatch_session=self.enter_context(
                    network.null_requests_session()
                )
            )
        self.assertSequenceEqual(error_notes, error.exception.__notes__)

    @parameterized.named_parameters(
        dict(
            testcase_name="no_lint_config",
            config_data={},
            expected_results={},
        ),
        dict(
            testcase_name="sort_no_diff",
            config_data={
                "lint": {"sort": {}},
                "media": [{"name": "a"}, {"name": "b"}],
            },
            expected_results={},
        ),
        dict(
            testcase_name="sort_case_sensitive",
            config_data={
                "lint": {"sort": {"caseSensitive": True}},
                "media": [{"name": "b"}, {"name": "aa"}, {"name": "Az"}],
            },
            expected_results={
                "sort": textwrap.dedent(
                    """\
                    --- media-names
                    +++ media-names-sorted
                    @@ -1,3 +1,3 @@
                    +- Az
                    +- aa
                     - b
                    -- aa
                    -- Az
                    """
                ),
            },
        ),
        dict(
            testcase_name="sort_case_insensitive",
            config_data={
                "lint": {"sort": {"caseSensitive": False}},
                "media": [{"name": "Az"}, {"name": "aa"}, {"name": "AA"}],
            },
            expected_results={
                "sort": textwrap.dedent(
                    """\
                    --- media-names
                    +++ media-names-sorted
                    @@ -1,3 +1,3 @@
                    +- AA
                    +- aa
                     - Az
                    -- aa
                    -- AA
                    """
                ),
            },
        ),
        dict(
            testcase_name="issues_report_empty",
            config_data={
                "reports": [
                    {
                        "name": "foo",
                        "sections": [
                            {"name": "bar", "filter": {"not": {"all": {}}}},
                        ],
                    }
                ],
                "lint": {"issuesReport": "foo"},
                "media": [{"name": "a"}],
            },
            expected_results={},
        ),
        dict(
            testcase_name="issues_report_not_empty",
            config_data={
                "reports": [
                    {
                        "name": "foo",
                        "sections": [
                            {"name": "bar", "filter": {"all": {}}},
                        ],
                    }
                ],
                "lint": {"issuesReport": "foo"},
                "media": [{"name": "a"}],
            },
            expected_results={"issuesReport": {"bar": [{"name": "a"}]}},
        ),
    )
    def test_lint(
        self,
        *,
        config_data: Any,
        expected_results: Any,
    ) -> None:
        self.enter_context(
            flagsaver.flagsaver(
                (
                    flags_and_constants.CONFIG_FILE,
                    self.create_tempfile(
                        content=json.dumps(config_data)
                    ).full_path,
                )
            )
        )
        config_ = config.Config.from_config_file(
            justwatch_session=self.enter_context(
                network.null_requests_session()
            )
        )

        results = config_.lint()

        self.assertEqual(expected_results, results)

    def test_example_config(self) -> None:
        with flagsaver.flagsaver(
            (
                flags_and_constants.CONFIG_FILE,
                str(
                    pathlib.Path(__file__).parent.parent / "config.example.yaml"
                ),
            )
        ):
            config_ = config.Config.from_config_file(
                justwatch_session=network.null_requests_session()
            )
            self.assertEmpty(config_.lint())


if __name__ == "__main__":
    absltest.main()
