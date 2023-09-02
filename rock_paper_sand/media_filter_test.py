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

from collections.abc import Mapping, Set

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format

from rock_paper_sand import config_pb2
from rock_paper_sand import media_filter


class _ExtraInfoFilter(media_filter.Filter):
    def __init__(self, extra: Set[str]):
        self._extra = extra

    def filter(
        self, media_item: config_pb2.MediaItem
    ) -> media_filter.FilterResult:
        """See base class."""
        return media_filter.FilterResult(True, extra=self._extra)


class MediaFilterTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="all",
            filter_by_name={},
            filter_config={"all": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="ref",
            filter_by_name=dict(foo=_ExtraInfoFilter({"foo"})),
            filter_config={"ref": "foo"},
            expected_result=media_filter.FilterResult(True, extra={"foo"}),
        ),
        dict(
            testcase_name="not_of_true",
            filter_by_name={},
            filter_config={"not": {"all": {}}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="not_of_false",
            filter_by_name=dict(foo=_ExtraInfoFilter({"foo"})),
            filter_config={"not": {"not": {"ref": "foo"}}},
            expected_result=media_filter.FilterResult(True, extra={"foo"}),
        ),
        dict(
            testcase_name="and_true",
            filter_by_name=dict(
                foo=_ExtraInfoFilter({"foo"}),
                bar=_ExtraInfoFilter({"bar"}),
            ),
            filter_config={
                "and": {
                    "filters": [
                        {"ref": "foo"},
                        {"ref": "bar"},
                    ]
                }
            },
            expected_result=media_filter.FilterResult(
                True, extra={"foo", "bar"}
            ),
        ),
        dict(
            testcase_name="and_false_with_short_circuit",
            filter_by_name=dict(foo=_ExtraInfoFilter({"foo"})),
            filter_config={
                "and": {
                    "filters": [
                        {"not": {"all": {}}},
                        {"ref": "foo"},
                    ]
                }
            },
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="or_true_with_short_circuit",
            filter_by_name=dict(
                foo=_ExtraInfoFilter({"foo"}),
                bar=_ExtraInfoFilter({"bar"}),
            ),
            filter_config={
                "or": {
                    "filters": [
                        {"not": {"all": {}}},
                        {"ref": "foo"},
                        {"ref": "bar"},
                    ]
                }
            },
            expected_result=media_filter.FilterResult(True, extra={"foo"}),
        ),
        dict(
            testcase_name="or_false",
            filter_by_name={},
            filter_config={
                "or": {
                    "filters": [
                        {"not": {"all": {}}},
                        {"not": {"all": {}}},
                    ]
                }
            },
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_availability_empty_matches",
            filter_by_name={},
            filter_config={"customAvailability": {"empty": True}},
            media_item=config_pb2.MediaItem(name="foo"),
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_not_empty_matches",
            filter_by_name={},
            filter_config={"customAvailability": {"empty": False}},
            media_item=config_pb2.MediaItem(
                name="foo", custom_availability="bar"
            ),
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_not_empty_no_match",
            filter_by_name={},
            filter_config={"customAvailability": {"empty": False}},
            media_item=config_pb2.MediaItem(name="foo"),
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_availability_equals_matches",
            filter_by_name={},
            filter_config={"customAvailability": {"equals": "bar"}},
            media_item=config_pb2.MediaItem(
                name="foo", custom_availability="bar"
            ),
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_equals_no_match",
            filter_by_name={},
            filter_config={"customAvailability": {"equals": "bar"}},
            media_item=config_pb2.MediaItem(name="foo"),
            expected_result=media_filter.FilterResult(False),
        ),
    )
    def test_basic_filter(
        self,
        *,
        filter_by_name: Mapping[str, media_filter.Filter],
        filter_config: ...,
        media_item: config_pb2.MediaItem = config_pb2.MediaItem(name="foo"),
        expected_result: media_filter.FilterResult,
    ):
        test_filter = media_filter.from_config(
            json_format.ParseDict(filter_config, config_pb2.Filter()),
            filter_by_name=filter_by_name,
        )
        result = test_filter.filter(media_item)
        self.assertEqual(expected_result, result)

    def test_unspecified_filter(self):
        with self.assertRaisesRegex(ValueError, "Unknown filter type"):
            media_filter.from_config(config_pb2.Filter(), filter_by_name={})

    def test_unspecified_string_match(self):
        test_filter = media_filter.from_config(
            json_format.ParseDict(
                {"customAvailability": {}}, config_pb2.Filter()
            ),
            filter_by_name={},
        )
        with self.assertRaisesRegex(
            ValueError, "Unknown string field match type"
        ):
            test_filter.filter(config_pb2.MediaItem(name="foo"))


if __name__ == "__main__":
    absltest.main()
