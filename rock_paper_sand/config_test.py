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

from collections.abc import Mapping
import os
import pathlib
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import yaml

from rock_paper_sand import config
from rock_paper_sand import config_pb2


class ConfigTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="xdg_path",
            env=dict(XDG_FOO_HOME="/xdg/foo", HOME="/home/user"),
            expected_path=pathlib.Path("/xdg/foo/rock-paper-sand"),
        ),
        dict(
            testcase_name="relative_to_home",
            env=dict(HOME="/home/user"),
            expected_path=pathlib.Path("/home/user/foo/rock-paper-sand"),
        ),
    )
    def test_get_app_dir(
        self,
        env: Mapping[str, str],
        expected_path: pathlib.Path,
    ):
        with mock.patch.dict(os.environ, env, clear=True):
            actual_path = config._get_app_dir(
                xdg_variable_name="XDG_FOO_HOME",
                relative_fallback_path=pathlib.Path("foo"),
            )
        self.assertEqual(expected_path, actual_path)

    def test_get_app_dir_error(self):
        with self.assertRaisesRegex(ValueError, "No HOME directory"):
            with mock.patch.dict(os.environ, {}, clear=True):
                config._get_app_dir(
                    xdg_variable_name="XDG_FOO_HOME",
                    relative_fallback_path=pathlib.Path("foo"),
                )

    def test_example_config(self):
        with open(
            pathlib.Path(__file__).parent.parent / "config.example.yaml",
            mode="rb",
        ) as config_file:
            json_format.ParseDict(
                yaml.safe_load(config_file), config_pb2.Config()
            )


if __name__ == "__main__":
    absltest.main()
