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
"""Tools for subcommands."""

import abc
import argparse
from collections.abc import Callable


class Subcommand(abc.ABC):
    """Base class for subcommands.

    Attributes:
        parser: Parser for this subcommand.
    """

    def __init__(self, parser: argparse.ArgumentParser):
        """Initializer.

        Subclasses will generally add their arguments to the parser in this
        method.

        Args:
            parser: Parser for this subcommand.
        """
        self.parser = parser

    @abc.abstractmethod
    def run(self, args: argparse.Namespace):
        """Runs the subcommand."""
        raise NotImplementedError()


class ContainerSubcommand(Subcommand):
    """Subcommand that only contains other subcommands of itself."""

    def add_subcommand(
        self,
        subparsers: ...,
        subcommand_callback: Callable[[argparse.ArgumentParser], Subcommand],
        name: str,
        **add_parser_kwargs: ...,
    ):
        """Adds a subcommand."""
        subcommand_parser = subparsers.add_parser(name, **add_parser_kwargs)
        subcommand_instance = subcommand_callback(subcommand_parser)
        subcommand_parser.set_defaults(subcommand=subcommand_instance)

    def run(self, args: argparse.Namespace):
        """See base class."""
        if hasattr(args, "subcommand") and args.subcommand is not self:
            args.subcommand.run(args)
        else:
            self.parser.print_help()
