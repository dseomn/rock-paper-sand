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
"""Entrypoint for rock_paper_sand."""

from collections.abc import Sequence

from absl import app
from absl import flags
import yaml

from rock_paper_sand import config
from rock_paper_sand import flags_and_constants
from rock_paper_sand import network

flags.adopt_module_key_flags(flags_and_constants)


def main(args: Sequence[str]) -> None:
    if len(args) > 1:
        raise app.UsageError(f"Too many arguments: {args!r}")
    with network.requests_session() as session:
        config_ = config.Config.from_config_file(session=session)
        results = {
            name: report_.generate(config_.proto.media)
            for name, report_ in config_.reports.items()
        }
        print(
            yaml.safe_dump(
                results, sort_keys=False, allow_unicode=True, width=float("inf")
            )
        )


if __name__ == "__main__":
    app.run(main)
