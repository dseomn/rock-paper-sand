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
"""Config commands."""

import argparse
import sys
import typing

import yaml

from rock_paper_sand import config
from rock_paper_sand import network
from rock_paper_sand import subcommand


class Lint(subcommand.Subcommand):
    """Lints the config file."""

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        del args  # Unused.
        with network.null_requests_session() as session:
            config_ = config.Config.from_config_file(
                wikidata_session=session,
                justwatch_session=session,
            )
            if results := config_.lint():
                print(
                    yaml.safe_dump(
                        results,
                        default_style="|",
                        sort_keys=False,
                        allow_unicode=True,
                        width=typing.cast(int, float("inf")),
                    ),
                    end="",
                )
                sys.exit(1)


class Main(subcommand.ContainerSubcommand):
    """Main config command."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            Lint,
            "lint",
            help="Lint the config file.",
        )
