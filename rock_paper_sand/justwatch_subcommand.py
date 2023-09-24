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
import json
import sys
from typing import IO

import yaml

from rock_paper_sand import justwatch
from rock_paper_sand import network
from rock_paper_sand import subcommand


def _add_locale_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--locale", help="JustWatch locale.", required=True)


class Locales(subcommand.Subcommand):
    """Prints the available JustWatch locales."""

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        del args  # Unused.
        with network.requests_session() as session:
            api = justwatch.Api(session=session)
            print(yaml.safe_dump(sorted(api.locales())), end="")


class MonetizationTypes(subcommand.Subcommand):
    """Prints the available JustWatch monetization types."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        _add_locale_arg(parser)

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        with network.requests_session() as session:
            api = justwatch.Api(session=session)
            print(
                yaml.safe_dump(
                    sorted(api.monetization_types(locale=args.locale))
                ),
                end="",
            )


class Providers(subcommand.Subcommand):
    """Prints the available JustWatch providers."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        _add_locale_arg(parser)

    def run(self, args: argparse.Namespace) -> None:
        """See base class."""
        with network.requests_session() as session:
            api = justwatch.Api(session=session)
            print(yaml.safe_dump(api.providers(locale=args.locale)), end="")


class Search(subcommand.Subcommand):
    """Searches for a media item."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        _add_locale_arg(parser)
        parser.add_argument("query", help="Search terms.", nargs="+")

    def run(
        self,
        args: argparse.Namespace,
        *,
        out_file: IO[str] = sys.stdout,
        api: justwatch.Api | None = None,
    ) -> None:
        """See base class."""
        with network.requests_session() as session:
            if api is None:
                api = justwatch.Api(session=session)
            results = api.post(
                f"titles/{args.locale}/popular",
                {"query": " ".join(args.query)},
            )
            for result in results["items"]:
                original_release_year = result.get("original_release_year", "?")
                years = (
                    original_release_year
                    if result["object_type"] == "movie"
                    else f"{original_release_year} - ?"
                )
                name = f"{result['title']} ({years})"
                name_json = json.dumps(name, ensure_ascii=False)
                justwatch_id = f"{result['object_type']}/{result['id']}"
                url = f"https://www.justwatch.com{result['full_path']}"
                print(f"- name: {name_json}", file=out_file)
                print(f"  justwatchId: {justwatch_id}  # {url}", file=out_file)


class Main(subcommand.ContainerSubcommand):
    """Main JustWatch API command."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        """See base class."""
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        self.add_subcommand(
            subparsers,
            Locales,
            "locales",
            help="Print the available JustWatch locales.",
        )
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
        self.add_subcommand(
            subparsers,
            Search,
            "search",
            help="Search for a media item.",
        )
