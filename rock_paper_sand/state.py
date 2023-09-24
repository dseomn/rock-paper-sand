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
"""State handling code."""

import os
import pathlib
import tempfile

from rock_paper_sand import flags_and_constants
from rock_paper_sand.proto import state_pb2


def from_file() -> state_pb2.State:
    """Returns the state from the state file, or empty state if none exists."""
    try:
        with open(flags_and_constants.STATE_FILE.value, "rb") as state_file:
            return state_pb2.State.FromString(state_file.read())
    except FileNotFoundError:
        return state_pb2.State()


def to_file(state: state_pb2.State) -> None:
    """Saves the state to the state file."""
    state_path = pathlib.Path(flags_and_constants.STATE_FILE.value)
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=state_path.parent,
        delete=False,
    ) as new_state_file:
        new_state_file.write(state.SerializeToString())
    os.replace(new_state_file.name, state_path)
