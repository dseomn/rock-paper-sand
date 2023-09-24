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

from collections.abc import Mapping
import os
import pathlib
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import flags_and_constants


class FlagsAndConstantsTest(parameterized.TestCase):
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
    ) -> None:
        with mock.patch.dict(os.environ, env, clear=True):
            actual_path = flags_and_constants._get_app_dir(  # pylint: disable=protected-access
                xdg_variable_name="XDG_FOO_HOME",
                relative_fallback_path=pathlib.Path("foo"),
            )
        self.assertEqual(expected_path, actual_path)

    def test_get_app_dir_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "No HOME directory"):
            with mock.patch.dict(os.environ, {}, clear=True):
                flags_and_constants._get_app_dir(  # pylint: disable=protected-access
                    xdg_variable_name="XDG_FOO_HOME",
                    relative_fallback_path=pathlib.Path("foo"),
                )


if __name__ == "__main__":
    absltest.main()
