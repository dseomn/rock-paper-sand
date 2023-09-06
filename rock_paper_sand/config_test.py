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

import pathlib

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized
from google.protobuf import json_format
import yaml

from rock_paper_sand import config
from rock_paper_sand import flags_and_constants
from rock_paper_sand import network


class ConfigTest(parameterized.TestCase):
    def test_example_config(self):
        with flagsaver.flagsaver(
            (
                flags_and_constants.CONFIG_FILE,
                str(
                    pathlib.Path(__file__).parent.parent / "config.example.yaml"
                ),
            )
        ):
            config.Config.from_config_file(
                session=network.null_requests_session()
            )


if __name__ == "__main__":
    absltest.main()
