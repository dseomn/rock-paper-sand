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
"""JustWatch commands."""

import argparse

import yaml

from rock_paper_sand import justwatch
from rock_paper_sand import network
from rock_paper_sand import subcommand


def _add_country_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", help="JustWatch country.", required=True)


class MonetizationTypes(subcommand.Subcommand):
    """Prints the available JustWatch monetization types."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        _add_country_arg(parser)

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        with network.requests_session() as session:
            api = justwatch.Api(session=session)
            print(
                yaml.safe_dump(
                    sorted(api.monetization_types(country=args.country))
                ),
                end="",
            )


class Providers(subcommand.Subcommand):
    """Prints the available JustWatch providers."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        _add_country_arg(parser)

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        with network.requests_session() as session:
            api = justwatch.Api(session=session)
            print(yaml.safe_dump(api.providers(country=args.country)), end="")


class Main(subcommand.ContainerSubcommand):
    """Main JustWatch API command."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            MonetizationTypes,
            "monetizationTypes",
            help="Print the available JustWatch monetization types.",
        )
        self.add_subcommand(
            subparsers,
            Providers,
            "providers",
            help="Print the available JustWatch providers.",
        )
