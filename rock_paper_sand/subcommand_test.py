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

import argparse
from collections.abc import Mapping
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import subcommand


class _TestContainer(subcommand.ContainerSubcommand):
    def __init__(
        self,
        parser: argparse.ArgumentParser,
        *,
        mock_subcommands: Mapping[str, type[subcommand.Subcommand]]
    ) -> None:
        super().__init__(parser)
        subparsers = parser.add_subparsers()
        for name, mock_subcommand_class in mock_subcommands.items():
            self.add_subcommand(subparsers, mock_subcommand_class, name)


class SubcommandTest(parameterized.TestCase):
    def test_container_runs_subcommand(self) -> None:
        mock_subcommand_class = mock.create_autospec(
            subcommand.Subcommand, spec_set=True
        )
        parser = argparse.ArgumentParser()
        container = _TestContainer(
            parser, mock_subcommands=dict(foo=mock_subcommand_class)
        )

        args = parser.parse_args(["foo"])
        container.run(args)

        mock_subcommand_class.return_value.run.assert_called_once_with(args)

    def test_container_prints_help(self) -> None:
        parser = argparse.ArgumentParser()
        mock_print_help = self.enter_context(
            mock.patch.object(
                parser, "print_help", autospec=True, spec_set=True
            )
        )
        container = _TestContainer(parser, mock_subcommands={})

        args = parser.parse_args([])
        container.run(args)

        mock_print_help.assert_called_once_with()


if __name__ == "__main__":
    absltest.main()
