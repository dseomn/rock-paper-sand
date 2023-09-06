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
import difflib
import sys

import yaml

from rock_paper_sand import config
from rock_paper_sand import network
from rock_paper_sand import subcommand


class MediaIsSorted(subcommand.Subcommand):
    """Checks if the media list is sorted."""

    def run(self, args: argparse.Namespace):
        """See base class."""
        del args  # Unused.
        with network.null_requests_session() as session:
            config_ = config.Config.from_config_file(session=session)
            names = tuple(item.name for item in config_.proto.media)
        sys.stdout.writelines(
            difflib.unified_diff(
                yaml.safe_dump(
                    names, allow_unicode=True, width=float("inf")
                ).splitlines(keepends=True),
                yaml.safe_dump(
                    sorted(names), allow_unicode=True, width=float("inf")
                ).splitlines(keepends=True),
                fromfile="media-names",
                tofile="media-names-sorted",
            )
        )


class Main(subcommand.ContainerSubcommand):
    """Main config command."""

    def __init__(self, parser: argparse.ArgumentParser):
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            MediaIsSorted,
            "media-is-sorted",
            help=(
                "Checks if the media list is sorted, and prints a diff if not."
            ),
        )
