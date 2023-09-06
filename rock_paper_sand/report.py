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
from typing import Any

from rock_paper_sand import config_pb2
from rock_paper_sand import media_filter


def _filter_media_item(
    filter_: media_filter.Filter,
    item: config_pb2.MediaItem,
) -> Mapping[str, Any] | None:
    """Returns info about the item if it matches, or None if it doesn't."""
    parts = []
    matched_any_part = False
    for part in item.parts:
        part_result = _filter_media_item(filter_, part)
        if part_result is None:
            parts.append(f"unmatched part: {part.name}")
        else:
            matched_any_part = True
            parts.append(part_result)
    item_result = filter_.filter(item)
    if not item_result.matches and not matched_any_part:
        return None
    result = {"name": item.name}
    if item.comment:
        result["comment"] = item.comment
    if item.done:
        result["done"] = item.done
    if item.custom_availability:
        result["customAvailability"] = item.custom_availability
    extra_information = []
    if not item_result.matches:
        extra_information.append("parent did not match, but children did")
    extra_information.extend(sorted(item_result.extra))
    if extra_information:
        result["extraInformation"] = extra_information
    if parts:
        result["parts"] = parts
    return result


class Report:
    """A report about the media."""

    def __init__(
        self,
        report_config: config_pb2.Report,
        *,
        filter_registry: media_filter.Registry,
    ):
        self._sections = {}
        for section in report_config.sections:
            self._sections[section.name] = filter_registry.parse(section.filter)

    def generate(
        self, media: Sequence[config_pb2.MediaItem]
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
