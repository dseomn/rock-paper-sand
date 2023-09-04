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
import functools

from absl import app
from absl import flags
from google.protobuf import json_format
import yaml

from rock_paper_sand import config
from rock_paper_sand import config_pb2
from rock_paper_sand import justwatch
from rock_paper_sand import media_filter
from rock_paper_sand import network
from rock_paper_sand import report

flags.adopt_module_key_flags(config)


def main(args: Sequence[str]) -> None:
    if len(args) > 1:
        raise app.UsageError(f"Too many arguments: {args!r}")
    with open(config.CONFIG_FILE.value, "rb") as config_file:
        config_ = json_format.ParseDict(
            yaml.safe_load(config_file), config_pb2.Config()
        )
    with network.requests_session() as session:
        justwatch_api = justwatch.Api(session=session)
        filter_registry = media_filter.Registry(
            justwatch_factory=functools.partial(
                justwatch.Filter, api=justwatch_api
            ),
        )
        for filter_config in config_.filters:
            filter_registry.register(
                filter_config.name, filter_registry.parse(filter_config.filter)
            )
        reports = {
            report_config.name: report.Report(
                report_config, filter_registry=filter_registry
            )
            for report_config in config_.reports
        }
        results = {
            name: report_.generate(config_.media)
            for name, report_ in reports.items()
        }
        print(
            yaml.safe_dump(
                results, sort_keys=False, allow_unicode=True, width=float("inf")
            )
        )


if __name__ == "__main__":
    app.run(main)
