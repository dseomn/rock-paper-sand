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
"""Reports commands."""

import argparse
from collections.abc import Generator
import contextlib
import typing
from typing import Any

import yaml

from rock_paper_sand import config
from rock_paper_sand import justwatch
from rock_paper_sand import state
from rock_paper_sand import subcommand
from rock_paper_sand import wikidata


@contextlib.contextmanager
def _config() -> Generator[config.Config, None, None]:
    with contextlib.ExitStack() as stack:
        yield config.Config.from_config_file(
            wikidata_session=stack.enter_context(wikidata.requests_session()),
            justwatch_session=stack.enter_context(justwatch.requests_session()),
        )


class Notify(subcommand.Subcommand):
    """Sends report notifications."""

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        del args  # Unused.
        with _config() as config_:
            state_ = state.from_file()
            for report_name, report_ in config_.reports.items():
                report_.notify(
                    report_.generate(config_.media),
                    report_state=state_.reports[report_name],
                )
                state.to_file(state_)


class Print(subcommand.Subcommand):
    """Prints the output of reports."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        parser.add_argument(
            "report",
            default=None,
            help="Report to print. Default: all.",
            nargs="?",
        )

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        with _config() as config_:
            results: Any
            if args.report is None:
                results = {
                    name: report_.generate(config_.media)
                    for name, report_ in config_.reports.items()
                }
            else:
                results = config_.reports[args.report].generate(config_.media)
            print(
                yaml.safe_dump(
                    results,
                    sort_keys=False,
                    allow_unicode=True,
                    width=typing.cast(int, float("inf")),
                ),
                end="",
            )


class Main(subcommand.ContainerSubcommand):
    """Main reports command."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            Notify,
            "notify",
            help="Send report notifications.",
        )
        self.add_subcommand(
            subparsers,
            Print,
            "print",
            help="Print the result of reports.",
        )
