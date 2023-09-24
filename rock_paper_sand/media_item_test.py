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
                proto=proto,
                done=mock.ANY,
                parts=(
                    media_item.MediaItem(
                        proto=config_pb2.MediaItem(name="some-part"),
                        done=mock.ANY,
                        parts=(),
                    ),
                ),
            ),
            item,
        )
        self.assertIn(multi_level_set.parse_number("1"), item.done)
        self.assertNotIn(multi_level_set.parse_number("1"), item.parts[0].done)


if __name__ == "__main__":
    absltest.main()
