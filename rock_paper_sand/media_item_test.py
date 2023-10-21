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
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format

from rock_paper_sand import media_item
from rock_paper_sand import multi_level_set
from rock_paper_sand.proto import config_pb2


class MediaItemTest(parameterized.TestCase):
    def test_from_config(self) -> None:
        proto = json_format.ParseDict(
            {
                "name": "some-name",
                "customData": {"a": "b"},
                "done": "all",
                "parts": [
                    {"name": "some-part"},
                ],
            },
            config_pb2.MediaItem(),
        )

        item = media_item.MediaItem.from_config(proto)

        self.assertEqual(
            media_item.MediaItem(
                id=mock.ANY,
                debug_description="unknown media item with name 'some-name'",
                proto=proto,
                fully_qualified_name="some-name",
                custom_data={"a": "b"},
                done=mock.ANY,
                wikidata_qid="",
                parts=(
                    media_item.MediaItem(
                        id=mock.ANY,
                        debug_description=(
                            "unknown media item with name 'some-part'"
                        ),
                        proto=config_pb2.MediaItem(name="some-part"),
                        fully_qualified_name="some-name: some-part",
                        custom_data=None,
                        done=mock.ANY,
                        wikidata_qid="",
                        parts=(),
                    ),
                ),
            ),
            item,
        )
        self.assertIn(multi_level_set.parse_number("1"), item.done)
        self.assertNotIn(multi_level_set.parse_number("1"), item.parts[0].done)

    def test_id(self) -> None:
        self.assertNotEqual(
            media_item.MediaItem.from_config(config_pb2.MediaItem(name="foo")),
            media_item.MediaItem.from_config(config_pb2.MediaItem(name="foo")),
        )

    @parameterized.named_parameters(
        dict(
            testcase_name="from_config",
            index=(42,),
            error_notes=("In media[42].parts[0].parts[1] with name ''.",),
        ),
        dict(
            testcase_name="from_code",
            index=(),
            error_notes=("In unknown media item with name ''.",),
        ),
    )
    def test_missing_name(
        self,
        *,
        index: Sequence[int],
        error_notes: Sequence[str],
    ) -> None:
        with self.assertRaisesRegex(
            ValueError, "name field is required"
        ) as error:
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {
                        "name": "foo",
                        "parts": [
                            {
                                "name": "foo",
                                "parts": [{"name": "foo"}, {}],
                            },
                        ],
                    },
                    config_pb2.MediaItem(),
                ),
                index=index,
            )
        self.assertSequenceEqual(error_notes, error.exception.__notes__)

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
    def test_invalid_wikidata_field(self, value: str) -> None:
        with self.assertRaisesRegex(ValueError, "Wikidata field"):
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {"name": "foo", "wikidata": value},
                    config_pb2.MediaItem(),
                )
            )

    @parameterized.parameters(
        ("", ""),
        ("Q1", "Q1"),
        ("https://www.wikidata.org/wiki/Q1", "Q1"),
    )
    def test_valid_wikidata_field(self, value: str, expected_qid: str) -> None:
        item = media_item.MediaItem.from_config(
            json_format.ParseDict(
                {"name": "foo", "wikidata": value},
                config_pb2.MediaItem(),
            )
        )
        self.assertEqual(expected_qid, item.wikidata_qid)

    def test_iter_all_items(self) -> None:
        item_1 = media_item.MediaItem.from_config(
            json_format.ParseDict(
                {
                    "name": "some-name",
                    "parts": [{"name": "some-part"}],
                },
                config_pb2.MediaItem(),
            )
        )
        item_2 = media_item.MediaItem.from_config(
            json_format.ParseDict(
                {"name": "some-other-name"},
                config_pb2.MediaItem(),
            )
        )

        self.assertSequenceEqual(
            (item_1, *item_1.parts, item_2),
            tuple(media_item.iter_all_items((item_1, item_2))),
        )


if __name__ == "__main__":
    absltest.main()
