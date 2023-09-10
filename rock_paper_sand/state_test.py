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

from rock_paper_sand import flags_and_constants
from rock_paper_sand import state
from rock_paper_sand.proto import state_pb2


class StateTest(parameterized.TestCase):
    def setUp(self):
        super().setUp()
        self._state_path = (
            pathlib.Path(self.create_tempdir("state").full_path)
            / "new-dir"
            / "new-file.binpb"
        )
        self.enter_context(
            flagsaver.flagsaver(
                (flags_and_constants.STATE_FILE, str(self._state_path))
            )
        )

    def test_from_file_not_found(self):
        self.assertEqual(state_pb2.State(), state.from_file())

    def test_round_trip(self):
        state_to_write = state_pb2.State(
            reports={
                "foo": state_pb2.ReportState(
                    previous_results_by_section_name={"bar": "baz"}
                )
            }
        )

        state.to_file(state_to_write)
        state_from_file = state.from_file()

        self.assertEqual(state_to_write, state_from_file)
        self.assertTrue(self._state_path.exists())


if __name__ == "__main__":
    absltest.main()
