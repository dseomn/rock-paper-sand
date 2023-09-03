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
"""Configuration."""

import os
import pathlib

from absl import flags


def _get_app_dir(
    xdg_variable_name: str,
    relative_fallback_path: pathlib.Path,
) -> pathlib.Path:
    # https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    relative_app_path = pathlib.Path("rock-paper-sand")
    xdg_path = os.getenv(xdg_variable_name)
    if xdg_path:  # Neither None nor empty
        return pathlib.Path(xdg_path) / relative_app_path
    home = os.getenv("HOME")
    if not home:  # Either None or empty
        raise ValueError("No HOME directory.")
    return pathlib.Path(home) / relative_fallback_path / relative_app_path


CONFIG_FILE = flags.DEFINE_string(
    "config_file",
    default=str(
        _get_app_dir("XDG_CONFIG_HOME", pathlib.Path(".config")) / "config.yaml"
    ),
    help="Path to config file.",
)
