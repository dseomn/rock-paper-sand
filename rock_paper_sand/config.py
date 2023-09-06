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

from collections.abc import Mapping
import dataclasses
import functools
from typing import TypeVar

from google.protobuf import json_format
import requests
import yaml

from rock_paper_sand import config_pb2
from rock_paper_sand import flags_and_constants
from rock_paper_sand import justwatch
from rock_paper_sand import media_filter
from rock_paper_sand import report

_T = TypeVar("_T")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Config:
    """Fully parsed config.

    Attributes:
        proto: Parsed config proto.
        justwatch_api: JustWatch API.
        filter_registry: Filter registry populated from the config file.
        reports: Mapping from report name to report.
    """

    proto: config_pb2.Config
    justwatch_api: justwatch.Api
    filter_registry: media_filter.Registry
    reports: Mapping[str, report.Report]

    @classmethod
    def from_config_file(
        cls: type[_T],
        *,
        session: requests.Session,
    ) -> _T:
        """Parses a config file."""
        with open(flags_and_constants.CONFIG_FILE.value, "rb") as config_file:
            proto = json_format.ParseDict(
                yaml.safe_load(config_file), config_pb2.Config()
            )
        justwatch_api = justwatch.Api(session=session)
        filter_registry = media_filter.Registry(
            justwatch_factory=functools.partial(
                justwatch.Filter, api=justwatch_api
            ),
        )
        for filter_config in proto.filters:
            filter_registry.register(
                filter_config.name, filter_registry.parse(filter_config.filter)
            )
        reports = {
            report_config.name: report.Report(
                report_config, filter_registry=filter_registry
            )
            for report_config in proto.reports
        }
        return cls(
            proto=proto,
            justwatch_api=justwatch_api,
            filter_registry=filter_registry,
            reports=reports,
        )
