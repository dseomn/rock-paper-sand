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
import difflib
import functools
import typing
from typing import Any, Self

from google.protobuf import json_format
import requests
import yaml

from rock_paper_sand import flags_and_constants
from rock_paper_sand import justwatch
from rock_paper_sand import media_filter
from rock_paper_sand import report
from rock_paper_sand.proto import config_pb2


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
        cls,
        *,
        session: requests.Session,
    ) -> Self:
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

    def _lint_sort(self) -> dict[str, Any]:
        if not self.proto.lint.HasField("sort"):
            return {}
        names = [item.name for item in self.proto.media]
        names_sorted = sorted(
            names,
            key=(
                None
                if self.proto.lint.sort.case_sensitive
                else lambda name: (name.casefold(), name)
            ),
        )
        if names == names_sorted:
            return {}
        return {
            "sort": "".join(
                difflib.unified_diff(
                    yaml.safe_dump(
                        names,
                        allow_unicode=True,
                        width=typing.cast(int, float("inf")),
                    ).splitlines(keepends=True),
                    yaml.safe_dump(
                        names_sorted,
                        allow_unicode=True,
                        width=typing.cast(int, float("inf")),
                    ).splitlines(keepends=True),
                    fromfile="media-names",
                    tofile="media-names-sorted",
                )
            ),
        }

    def _lint_issues_report(self) -> dict[str, Any]:
        if not self.proto.lint.issues_report:
            return {}
        results = self.reports[self.proto.lint.issues_report].generate(
            self.proto.media
        )
        if not any(results.values()):
            return {}
        return {"issuesReport": results}

    def lint(self) -> Mapping[str, Any]:
        """Returns lint issues, if there are any."""
        return self._lint_sort() | self._lint_issues_report()
