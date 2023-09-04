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
from unittest import mock

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
            testcase_name="has_parts_true_matches",
            filter_by_name={},
            filter_config={"has_parts": True},
            media_item=config_pb2.MediaItem(
                name="foo",
                parts=[config_pb2.MediaItem(name="bar")],
            ),
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="has_parts_true_no_match",
            filter_by_name={},
            filter_config={"has_parts": True},
            media_item=config_pb2.MediaItem(name="foo"),
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
        registry = media_filter.Registry()
        for name, filter_ in filter_by_name.items():
            registry.register(name, filter_)
        test_filter = registry.parse(
            json_format.ParseDict(filter_config, config_pb2.Filter())
        )
        result = test_filter.filter(media_item)
        self.assertEqual(expected_result, result)

    def test_justwatch_filter(self):
        mock_filter = mock.create_autospec(
            media_filter.Filter, spec_set=True, instance=True
        )
        justwatch_factory = mock.Mock(spec_set=(), return_value=mock_filter)
        registry = media_filter.Registry(justwatch_factory=justwatch_factory)
        filter_config = json_format.ParseDict(
            {"justwatch": {"locale": "en_US"}}, config_pb2.Filter()
        )

        returned_filter = registry.parse(filter_config)

        justwatch_factory.assert_called_once_with(filter_config.justwatch)
        self.assertIs(mock_filter, returned_filter)

    def test_justwatch_filter_unsupported(self):
        registry = media_filter.Registry(justwatch_factory=None)
        with self.assertRaisesRegex(ValueError, "JustWatch.*no callback"):
            registry.parse(
                json_format.ParseDict({"justwatch": {}}, config_pb2.Filter())
            )

    def test_unspecified_filter(self):
        with self.assertRaisesRegex(ValueError, "Unknown filter type"):
            media_filter.Registry().parse(config_pb2.Filter())

    def test_unspecified_string_match(self):
        test_filter = media_filter.Registry().parse(
            json_format.ParseDict(
                {"customAvailability": {}}, config_pb2.Filter()
            )
        )
        with self.assertRaisesRegex(
            ValueError, "Unknown string field match type"
        ):
            test_filter.filter(config_pb2.MediaItem(name="foo"))

    def test_registry_unique(self):
        registry = media_filter.Registry()
        registry.register("foo", media_filter.And())
        with self.assertRaisesRegex(
            ValueError, "Filter 'foo' is defined multiple times"
        ):
            registry.register("foo", media_filter.And())


if __name__ == "__main__":
    absltest.main()
