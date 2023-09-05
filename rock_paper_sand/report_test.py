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

from collections.abc import Set

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format

from rock_paper_sand import config_pb2
from rock_paper_sand import media_filter
from rock_paper_sand import report


class _ExtraInfoFilter(media_filter.Filter):
    def __init__(self, extra: Set[str]):
        self._extra = extra

    def filter(
        self, media_item: config_pb2.MediaItem
    ) -> media_filter.FilterResult:
        """See base class."""
        return media_filter.FilterResult(True, extra=self._extra)


class ReportTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="simple",
            report_config={
                "sections": [
                    {"name": "all", "filter": {"all": {}}},
                    {"name": "none", "filter": {"not": {"all": {}}}},
                ]
            },
            media=[
                {"name": "foo", "comment": "FOO!", "done": "all"},
                {"name": "bar", "parts": [{"name": "quux"}]},
            ],
            expected_result={
                "all": [
                    {"name": "foo", "comment": "FOO!", "done": "all"},
                    {"name": "bar", "parts": [{"name": "quux"}]},
                ],
                "none": [],
            },
        ),
        dict(
            testcase_name="with_extra",
            report_config={
                "sections": [{"name": "extra", "filter": {"ref": "extra"}}]
            },
            media=[{"name": "foo"}],
            expected_result={
                "extra": [
                    {"name": "foo", "extraInformation": ["example extra info"]},
                ],
            },
        ),
        dict(
            testcase_name="partial_match",
            report_config={
                "sections": [
                    {
                        "name": "custom_availability",
                        "filter": {"customAvailability": {"empty": False}},
                    },
                ]
            },
            media=[
                {
                    "name": "unmatched_parent",
                    "parts": [
                        {"name": "matched_child", "customAvailability": "yes"},
                        {"name": "unmatched_child"},
                    ],
                },
                {
                    "name": "matched_parent",
                    "customAvailability": "yes",
                    "parts": [
                        {"name": "matched_child", "customAvailability": "yes"},
                        {"name": "unmatched_child"},
                    ],
                },
            ],
            expected_result={
                "custom_availability": [
                    {
                        "name": "unmatched_parent",
                        "extraInformation": [
                            "parent did not match, but children did",
                        ],
                        "parts": [
                            {
                                "name": "matched_child",
                                "customAvailability": "yes",
                            },
                            "unmatched part: unmatched_child",
                        ],
                    },
                    {
                        "name": "matched_parent",
                        "customAvailability": "yes",
                        "parts": [
                            {
                                "name": "matched_child",
                                "customAvailability": "yes",
                            },
                            "unmatched part: unmatched_child",
                        ],
                    },
                ],
            },
        ),
    )
    def test_report(
        self,
        report_config: ...,
        media: ...,
        expected_result: ...,
    ):
        filter_registry = media_filter.Registry()
        filter_registry.register(
            "extra", _ExtraInfoFilter({"example extra info"})
        )
        report_ = report.Report(
            json_format.ParseDict(report_config, config_pb2.Report()),
            filter_registry=filter_registry,
        )
        result = report_.generate(
            tuple(
                json_format.ParseDict(item, config_pb2.MediaItem())
                for item in media
            )
        )
        self.assertEqual(expected_result, result)


if __name__ == "__main__":
    absltest.main()
