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

from collections.abc import Mapping, Set
import itertools
import re
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict

from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand.proto import config_pb2


class _ExtraInfoFilter(media_filter.CachedFilter):
    """Test filter that returns the given extra info.

    Attributes:
        call_count: Number of times filter_implementation() was called.
    """

    def __init__(self, extra: Set[media_filter.ResultExtra]) -> None:
        super().__init__()
        self._extra = extra
        self.call_count = 0

    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return frozenset(
            itertools.chain.from_iterable(extra.data for extra in self._extra)
        )

    def filter_implementation(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        self.call_count += 1
        return media_filter.FilterResult(True, extra=self._extra)


_EXTRA_1 = media_filter.ResultExtra(
    data=immutabledict.immutabledict(test="extra-1"),
)
_EXTRA_2 = media_filter.ResultExtra(
    data=immutabledict.immutabledict(test="extra-2"),
)


class MediaFilterTest(parameterized.TestCase):
    def test_filter_request_cache_key(self) -> None:
        request = media_filter.FilterRequest(
            media_item.MediaItem.from_config(config_pb2.MediaItem(name="foo"))
        )
        self.assertEqual((request.item.id, request.now), request.cache_key())

    @parameterized.named_parameters(
        dict(
            testcase_name="all",
            filter_config={"all": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="ref",
            filter_by_name=dict(foo=_ExtraInfoFilter({_EXTRA_1})),
            filter_config={"ref": "foo"},
            expected_result=media_filter.FilterResult(True, extra={_EXTRA_1}),
        ),
        dict(
            testcase_name="not_of_true",
            filter_config={"not": {"all": {}}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="not_of_false",
            filter_by_name=dict(foo=_ExtraInfoFilter({_EXTRA_1})),
            filter_config={"not": {"not": {"ref": "foo"}}},
            expected_result=media_filter.FilterResult(True, extra={_EXTRA_1}),
        ),
        dict(
            testcase_name="and_true",
            filter_by_name=dict(
                foo=_ExtraInfoFilter({_EXTRA_1}),
                bar=_ExtraInfoFilter({_EXTRA_2}),
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
                True, extra={_EXTRA_1, _EXTRA_2}
            ),
        ),
        dict(
            testcase_name="and_false_without_short_circuit",
            filter_by_name=dict(foo=_ExtraInfoFilter({_EXTRA_1})),
            filter_config={
                "and": {
                    "filters": [
                        {"not": {"all": {}}},
                        {"ref": "foo"},
                    ]
                }
            },
            expected_result=media_filter.FilterResult(False, extra={_EXTRA_1}),
        ),
        dict(
            testcase_name="or_true_without_short_circuit",
            filter_by_name=dict(
                foo=_ExtraInfoFilter({_EXTRA_1}),
                bar=_ExtraInfoFilter({_EXTRA_2}),
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
            expected_result=media_filter.FilterResult(
                True, extra={_EXTRA_1, _EXTRA_2}
            ),
        ),
        dict(
            testcase_name="or_false",
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
            filter_config={"has_parts": True},
            item={"name": "foo", "parts": [{"name": "bar"}]},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="has_parts_true_no_match",
            filter_config={"has_parts": True},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="done_true",
            filter_config={"done": "all"},
            item={"name": "foo", "done": "1 - 5, all"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="done_false",
            filter_config={"done": "5.10"},
            item={"name": "foo", "done": "1 - 5.9"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="name_matches",
            filter_config={"name": {"equals": "foo"}},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_data_not_present",
            filter_config={"customData": {"jmespath": "bar == `42`"}},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_data_matches",
            filter_config={"customData": {"jmespath": "bar == `42`"}},
            item={"name": "foo", "customData": {"bar": 42}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_data_no_match",
            filter_config={"customData": {"jmespath": "bar == `7`"}},
            item={"name": "foo", "customData": {"bar": 42}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_availability_empty_matches",
            filter_config={"customAvailability": {"empty": True}},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_not_empty_matches",
            filter_config={"customAvailability": {"empty": False}},
            item={"name": "foo", "customAvailability": "bar"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_not_empty_no_match",
            filter_config={"customAvailability": {"empty": False}},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_availability_equals_matches",
            filter_config={"customAvailability": {"equals": "bar"}},
            item={"name": "foo", "customAvailability": "bar"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_equals_no_match",
            filter_config={"customAvailability": {"equals": "bar"}},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="custom_availability_regex_matches",
            filter_config={"customAvailability": {"regex": r"[Aa]"}},
            item={"name": "foo", "customAvailability": "bar"},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="custom_availability_regex_no_match",
            filter_config={"customAvailability": {"regex": r"[Zz]"}},
            item={"name": "foo", "customAvailability": "bar"},
            expected_result=media_filter.FilterResult(False),
        ),
    )
    def test_basic_filter(
        self,
        *,
        filter_by_name: Mapping[str, media_filter.Filter] = (
            immutabledict.immutabledict()
        ),
        filter_config: Any,
        item: Any = immutabledict.immutabledict({"name": "foo"}),
        expected_result: media_filter.FilterResult,
    ) -> None:
        registry = media_filter.Registry()
        for name, filter_ in filter_by_name.items():
            registry.register(name, filter_)
        test_filter = registry.parse(
            json_format.ParseDict(filter_config, config_pb2.Filter())
        )
        result = test_filter.filter(
            media_filter.FilterRequest(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(item, config_pb2.MediaItem())
                )
            )
        )
        self.assertEqual(expected_result, result)

    @parameterized.named_parameters(
        dict(
            testcase_name="ref",
            filter_by_name=dict(
                foo=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(some_key="bar")
                        )
                    }
                )
            ),
            filter_config={"ref": "foo"},
            valid_extra_keys={"some_key"},
        ),
        dict(
            testcase_name="not",
            filter_by_name=dict(
                foo=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(some_key="bar")
                        )
                    }
                )
            ),
            filter_config={"not": {"ref": "foo"}},
            valid_extra_keys={"some_key"},
        ),
        dict(
            testcase_name="and",
            filter_by_name=dict(
                foo=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(key_1="baz")
                        )
                    }
                ),
                bar=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(key_2="baz")
                        )
                    }
                ),
            ),
            filter_config={
                "and": {"filters": [{"ref": "foo"}, {"ref": "bar"}]}
            },
            valid_extra_keys={"key_1", "key_2"},
        ),
        dict(
            testcase_name="or",
            filter_by_name=dict(
                foo=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(key_1="baz")
                        )
                    }
                ),
                bar=_ExtraInfoFilter(
                    {
                        media_filter.ResultExtra(
                            data=immutabledict.immutabledict(key_2="baz")
                        )
                    }
                ),
            ),
            filter_config={"or": {"filters": [{"ref": "foo"}, {"ref": "bar"}]}},
            valid_extra_keys={"key_1", "key_2"},
        ),
        dict(
            testcase_name="has_parts",
            filter_config={"hasParts": True},
            valid_extra_keys=frozenset(),
        ),
    )
    def test_basic_filter_valid_extra_keys(
        self,
        *,
        filter_by_name: Mapping[str, media_filter.Filter] = (
            immutabledict.immutabledict()
        ),
        filter_config: Any,
        valid_extra_keys: Set[str],
    ) -> None:
        registry = media_filter.Registry()
        for name, filter_ in filter_by_name.items():
            registry.register(name, filter_)
        test_filter = registry.parse(
            json_format.ParseDict(filter_config, config_pb2.Filter())
        )
        self.assertEqual(valid_extra_keys, test_filter.valid_extra_keys())

    def test_cached_filter(self) -> None:
        test_filter = _ExtraInfoFilter({_EXTRA_1})
        request = media_filter.FilterRequest(
            media_item.MediaItem.from_config(config_pb2.MediaItem(name="bar"))
        )
        expected_result = media_filter.FilterResult(True, extra={_EXTRA_1})

        first_result = test_filter.filter(request)
        second_result = test_filter.filter(request)

        self.assertEqual(expected_result, first_result)
        self.assertEqual(expected_result, second_result)
        self.assertEqual(1, test_filter.call_count)

    @parameterized.parameters("wikidata", "justwatch")
    def test_factory_filter(self, name: str) -> None:
        mock_filter = mock.create_autospec(
            media_filter.Filter, spec_set=True, instance=True
        )
        factory = mock.Mock(spec_set=(), return_value=mock_filter)
        # TODO(https://github.com/pylint-dev/pylint/issues/9983): Remove disable
        registry = media_filter.Registry(**{f"{name}_factory": factory})  # fmt: skip; pylint: disable=unexpected-keyword-arg
        filter_config = json_format.ParseDict({name: {}}, config_pb2.Filter())

        returned_filter = registry.parse(filter_config)

        factory.assert_called_once_with(getattr(filter_config, name))
        self.assertIs(mock_filter, returned_filter)

    @parameterized.parameters("wikidata", "justwatch")
    def test_factory_filter_unsupported(self, name: str) -> None:
        # TODO(https://github.com/pylint-dev/pylint/issues/9983): Remove disable
        registry = media_filter.Registry(**{f"{name}_factory": None})  # fmt: skip; pylint: disable=unexpected-keyword-arg
        with self.assertRaisesRegex(ValueError, "no callback"):
            registry.parse(
                json_format.ParseDict({name: {}}, config_pb2.Filter())
            )

    @parameterized.named_parameters(
        dict(
            testcase_name="unspecified_filter",
            filter_config={},
            error_class=ValueError,
            error_regex="Unknown filter type",
        ),
        dict(
            testcase_name="unspecified_string_match",
            filter_config={"customAvailability": {}},
            error_class=ValueError,
            error_regex="Unknown string field match type",
        ),
        dict(
            testcase_name="invalid_regex",
            filter_config={"customAvailability": {"regex": "("}},
            error_class=re.error,
            error_regex="",
        ),
        dict(
            testcase_name="unspecified_data_match",
            filter_config={"customData": {}},
            error_class=ValueError,
            error_regex="Unknown arbitrary data match type",
        ),
    )
    def test_parse_error(
        self,
        *,
        filter_config: Any,
        error_class: type[Exception],
        error_regex: str,
    ) -> None:
        with self.assertRaisesRegex(error_class, error_regex):
            media_filter.Registry().parse(
                json_format.ParseDict(filter_config, config_pb2.Filter())
            )

    def test_jmespath_wrong_return_type(self) -> None:
        test_filter = media_filter.Registry().parse(
            json_format.ParseDict(
                {"customData": {"jmespath": "bar"}}, config_pb2.Filter()
            )
        )
        request = media_filter.FilterRequest(
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {"name": "foo", "customData": {"bar": 42}},
                    config_pb2.MediaItem(),
                )
            )
        )

        with self.assertRaisesRegex(ValueError, "JMESPath .* invalid value"):
            test_filter.filter(request)

    def test_registry_unique(self) -> None:
        registry = media_filter.Registry()
        registry.register("foo", media_filter.BinaryLogic(op=all))
        with self.assertRaisesRegex(
            ValueError, "Filter 'foo' is defined multiple times"
        ):
            registry.register("foo", media_filter.BinaryLogic(op=all))


if __name__ == "__main__":
    absltest.main()
