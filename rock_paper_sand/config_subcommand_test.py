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
import io
import json
import textwrap

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized

from rock_paper_sand import config_subcommand
from rock_paper_sand import flags_and_constants


class ConfigSubcommandTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="no_diff",
            config_data={"media": [{"name": "a"}, {"name": "b"}]},
            expected_output="",
        ),
        dict(
            testcase_name="diff",
            config_data={"media": [{"name": "b"}, {"name": "a"}]},
            expected_output=textwrap.dedent(
                """\
                --- media-names
                +++ media-names-sorted
                @@ -1,2 +1,2 @@
                +- a
                 - b
                -- a
                """
            ),
        ),
    )
    def test_media_is_sorted(
        self,
        *,
        config_data: ...,
        expected_output: str,
    ):
        parser = argparse.ArgumentParser()
        self.enter_context(
            flagsaver.flagsaver(
                (
                    flags_and_constants.CONFIG_FILE,
                    self.create_tempfile(
                        content=json.dumps(config_data)
                    ).full_path,
                )
            )
        )
        output = io.StringIO()

        command = config_subcommand.MediaIsSorted(parser)
        command.run(parser.parse_args([]), out_file=output)

        self.assertEqual(expected_output, output.getvalue())


if __name__ == "__main__":
    absltest.main()
