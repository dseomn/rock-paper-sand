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
"""Reports about media."""

from collections.abc import Mapping, Sequence
import difflib
import email.message
import json
import subprocess
import typing
from typing import Any

import yaml

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand.proto import config_pb2
from rock_paper_sand.proto import state_pb2


def _filter_media_item(
    filter_: media_filter.Filter,
    item: media_item.MediaItem,
) -> Mapping[str, Any] | None:
    """Returns info about the item if it matches, or None if it doesn't."""
    parts: list[Any] = []
    matched_any_part = False
    for part in item.parts:
        part_result = _filter_media_item(filter_, part)
        if part_result is None:
            parts.append(f"unmatched part: {part.proto.name}")
        else:
            matched_any_part = True
            parts.append(part_result)
    item_result = filter_.filter(item)
    if not item_result.matches and not matched_any_part:
        return None
    result: dict[str, Any] = {"name": item.proto.name}
    if item.proto.comment:
        result["comment"] = item.proto.comment
    if item.proto.done:
        result["done"] = item.proto.done
    if item.proto.custom_availability:
        result["customAvailability"] = item.proto.custom_availability
    extra_information = []
    if not item_result.matches:
        extra_information.append("parent did not match, but children did")
    extra_information.extend(
        sorted(
            extra_str
            for extra in item_result.extra
            if (extra_str := extra.human_readable()) is not None
        )
    )
    if extra_information:
        result["extraInformation"] = extra_information
    if parts:
        result["parts"] = parts
    return result


def _dump_for_email(results: Any) -> str:
    return yaml.safe_dump(
        results,
        sort_keys=False,
        allow_unicode=True,
        width=typing.cast(int, float("inf")),
    )


def _add_diff_attachment(
    *,
    message: email.message.EmailMessage,
    name: str,
    old: str | None,
    new: str | None,
    collapse: bool = False,
) -> None:
    if old is None:
        content = f"Section {name} is newly created"
    elif new is None:
        content = f"Section {name} was deleted"
    elif collapse:
        content = f"Section {name} differs"
    else:
        content = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"{name}.yaml.old",
                tofile=f"{name}.yaml",
            )
        )
    message.add_attachment(
        content,
        disposition="inline",
        filename=f"{name}.diff",
    )


class Report:
    """A report about the media."""

    def __init__(
        self,
        report_config: config_pb2.Report,
        *,
        filter_registry: media_filter.Registry,
    ) -> None:
        self._config = report_config
        self._sections: dict[str, media_filter.Filter] = {}
        self._collapse_diff_sections: set[str] = set()
        for section_index, section in enumerate(report_config.sections):
            with exceptions.add_note(
                f"In sections[{section_index}] with name {section.name!r}."
            ):
                if not section.name:
                    raise ValueError("The name field is required.")
                if section.name in self._sections:
                    raise ValueError("The name field must be unique.")
                self._sections[section.name] = filter_registry.parse(
                    section.filter
                )
                if section.collapse_diff:
                    self._collapse_diff_sections.add(section.name)

    def generate(
        self, media: Sequence[media_item.MediaItem]
    ) -> Mapping[str, Any]:
        """Returns a mapping from section name to results of the section."""
        result = {}
        for section_name, section_filter in self._sections.items():
            section_results = []
            for item in media:
                item_result = _filter_media_item(section_filter, item)
                if item_result is not None:
                    section_results.append(item_result)
            result[section_name] = section_results
        return result

    def notify(
        self,
        results: Mapping[str, Any],
        *,
        report_state: state_pb2.ReportState,
        subprocess_run: Any = subprocess.run,
    ) -> None:
        """Sends any notifications defined in the report.

        Args:
            results: Return value from self.generate().
            report_state: State for the report, which this function will modify
                as needed.
            subprocess_run: subprocess.run or a mock of it.
        """
        # Note that this function uses text/plain (default for str arguments)
        # instead of more specific mime types so that email clients actually
        # show the text instead of (only) offering to download the attachment.
        if not self._config.email_headers:
            return
        previous_results = {
            k: json.loads(d)
            for k, d in report_state.previous_results_by_section_name.items()
        }
        if results == previous_results:
            return
        message = email.message.EmailMessage()
        message["Subject"] = f"rock-paper-sand report {self._config.name}"
        for header, value in self._config.email_headers.items():
            message[header] = value
        message["Rock-Paper-Sand-Report-Name"] = self._config.name
        message.add_attachment(self._config.email_body, disposition="inline")
        for section_name, section_results in results.items():
            if section_name not in previous_results:
                section_previous_results = None
            elif section_results == previous_results[section_name]:
                continue
            else:
                section_previous_results = _dump_for_email(
                    previous_results[section_name]
                )
            _add_diff_attachment(
                message=message,
                name=section_name,
                old=section_previous_results,
                new=_dump_for_email(section_results),
                collapse=section_name in self._collapse_diff_sections,
            )
        for section_name, section_results in previous_results.items():
            if section_name not in results:
                _add_diff_attachment(
                    message=message,
                    name=section_name,
                    old=_dump_for_email(section_results),
                    new=None,
                )
        for section_name, section_results in results.items():
            message.add_attachment(
                _dump_for_email(section_results),
                disposition="inline",
                filename=f"{section_name}.yaml",
            )
        subprocess_run(
            ("/usr/sbin/sendmail", "-i", "-t"),
            check=True,
            input=bytes(message),
        )
        report_state.previous_results_by_section_name.clear()
        report_state.previous_results_by_section_name.update(
            (section_name, json.dumps(section_results))
            for section_name, section_results in results.items()
        )
