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

import collections
from collections.abc import Mapping, Sequence
import copy
import dataclasses
import datetime
import difflib
import email.message
import json
import subprocess
import typing
from typing import Any, Self

import yaml

from rock_paper_sand import exceptions
from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand.proto import config_pb2
from rock_paper_sand.proto import state_pb2


def _filter_media_item(
    filter_: media_filter.Filter,
    item: media_item.MediaItem,
    *,
    now: datetime.datetime,
) -> Mapping[str, Any] | None:
    """Returns info about the item if it matches, or None if it doesn't."""
    parts: list[Any] = []
    matched_any_part = False
    for part in item.parts:
        part_result = _filter_media_item(filter_, part, now=now)
        if part_result is None:
            parts.append(f"unmatched part: {part.proto.name}")
        else:
            matched_any_part = True
            parts.append(part_result)
    item_result = filter_.filter(media_filter.FilterRequest(item, now=now))
    if not item_result.matches and not matched_any_part:
        return None
    result: dict[str, Any] = {"name": item.proto.name}
    if item.proto.comment:
        result["comment"] = item.proto.comment
    if item.custom_data is not None:
        # Copy to prevent yaml anchors and aliases when the same
        # item.custom_data appears in multiple places in a yaml document.
        result["customData"] = copy.deepcopy(item.custom_data)
    if item.proto.done:
        result["done"] = item.proto.done
    if item.proto.custom_availability:
        result["customAvailability"] = item.proto.custom_availability
    if item.proto.wikidata:
        result["wikidata"] = item.proto.wikidata
    if item.proto.justwatch:
        result["justwatch"] = item.proto.justwatch
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
) -> str:
    if old is None:
        content = f"Section {name} is newly created"
        diff_type = "created"
    elif new is None:
        content = f"Section {name} was deleted"
        diff_type = "deleted"
    elif collapse:
        content = f"Section {name} differs"
        diff_type = "collapsed"
    else:
        content = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"{name}.yaml.old",
                tofile=f"{name}.yaml",
                n=5,
            )
        )
        diff_type = "full"
    message.add_attachment(
        content,
        disposition="inline",
        filename=f"{name}.diff",
    )
    return diff_type


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Section:
    """Section of a report.

    Attributes:
        proto: Proto from the config file.
        filter: Parsed proto.filter field.
    """

    proto: config_pb2.Report.Section
    filter: media_filter.Filter

    @classmethod
    def from_config(
        cls,
        proto: config_pb2.Report.Section,
        *,
        filter_registry: media_filter.Registry,
    ) -> Self:
        if not proto.name:
            raise ValueError("The name field is required.")
        filter_ = filter_registry.parse(proto.filter)
        if proto.HasField("group_by"):
            if not proto.group_by.key:
                raise ValueError("The key field is required in group_by.")
            valid_keys = filter_.valid_extra_keys()
            if proto.group_by.key not in valid_keys:
                raise ValueError(
                    f"Group key {proto.group_by.key!r} is not a valid key for "
                    f"the specified filter. Valid keys: {sorted(valid_keys)}"
                )
        return cls(
            proto=proto,
            filter=filter_,
        )

    def _generate_group_by(
        self,
        media: Sequence[media_item.MediaItem],
        *,
        now: datetime.datetime,
    ) -> Any:
        results = collections.defaultdict(list)
        for item in media_item.iter_all_items(media):
            item_result = self.filter.filter(
                media_filter.FilterRequest(item, now=now)
            )
            if not item_result.matches:
                continue
            groups = {
                extra[self.proto.group_by.key]
                for extra in item_result.extra
                if self.proto.group_by.key in extra
            }
            for group in groups:
                results[group].append(item.fully_qualified_name)
        return {
            group: names
            for group, names in sorted(results.items(), key=lambda kv: kv[0])
        }

    def _generate_normal(
        self,
        media: Sequence[media_item.MediaItem],
        *,
        now: datetime.datetime,
    ) -> Any:
        return [
            result
            for item in media
            if (
                (result := _filter_media_item(self.filter, item, now=now))
                is not None
            )
        ]

    def generate(
        self,
        media: Sequence[media_item.MediaItem],
        *,
        now: datetime.datetime,
    ) -> Any:
        """Returns the section's results."""
        if self.proto.HasField("group_by"):
            return self._generate_group_by(media, now=now)
        else:
            return self._generate_normal(media, now=now)


class Report:
    """A report about the media."""

    def __init__(
        self,
        report_config: config_pb2.Report,
        *,
        filter_registry: media_filter.Registry,
    ) -> None:
        self._config = report_config
        self._sections: dict[str, _Section] = {}
        for section_index, section in enumerate(report_config.sections):
            with exceptions.add_note(
                f"In sections[{section_index}] with name {section.name!r}."
            ):
                if section.name in self._sections:
                    raise ValueError("The name field must be unique.")
                self._sections[section.name] = _Section.from_config(
                    section, filter_registry=filter_registry
                )

    def generate(
        self, media: Sequence[media_item.MediaItem]
    ) -> Mapping[str, Any]:
        """Returns a mapping from section name to results of the section."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        return {
            section_name: section.generate(media, now=now)
            for section_name, section in self._sections.items()
        }

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
        diff_types: set[str] = set()
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
            diff_types.add(
                _add_diff_attachment(
                    message=message,
                    name=section_name,
                    old=section_previous_results,
                    new=_dump_for_email(section_results),
                    collapse=self._sections[section_name].proto.collapse_diff,
                )
            )
        for section_name, section_results in previous_results.items():
            if section_name not in results:
                diff_types.add(
                    _add_diff_attachment(
                        message=message,
                        name=section_name,
                        old=_dump_for_email(section_results),
                        new=None,
                    )
                )
        for section_name, section_results in results.items():
            message.add_attachment(
                _dump_for_email(section_results),
                disposition="inline",
                filename=f"{section_name}.yaml",
            )
        message["Rock-Paper-Sand-Diff-Types"] = ", ".join(sorted(diff_types))
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
