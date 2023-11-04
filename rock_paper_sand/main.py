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

import argparse

from absl import flags
from absl import logging
from absl.flags import argparse_flags

from rock_paper_sand import config_subcommand
from rock_paper_sand import flags_and_constants
from rock_paper_sand import justwatch_subcommand
from rock_paper_sand import reports_subcommand
from rock_paper_sand import subcommand

flags.adopt_module_key_flags(flags_and_constants)


class MainCommand(subcommand.ContainerSubcommand):
    """Top-level container of subcommands."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            config_subcommand.Main,
            "config",
            help="Subcommand for working with the config file.",
        )
        self.add_subcommand(
            subparsers,
            justwatch_subcommand.Main,
            "justwatch",
            help="Subcommand for working with the JustWatch API.",
        )
        self.add_subcommand(
            subparsers,
            reports_subcommand.Main,
            "reports",
            help="Subcommand for working with reports.",
        )


def main() -> None:
    flags.FLAGS.set_default("logtostderr", True)
    logging.use_absl_handler()
    parser = argparse_flags.ArgumentParser()
    main_command = MainCommand(parser)
    args = parser.parse_args()
    main_command.run(args)


if __name__ == "__main__":
    main()
