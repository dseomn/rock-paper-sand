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
"""Multi-level sets."""

from collections.abc import Collection
from typing import NewType, Self

# Something like a season/episode number. E.g., season 2 would be (2,) and
# episode 3 of season 4 would be (4, 3). Earlier levels include all children, so
# (2,) includes (2, x) for any value of x, and () includes any MultiLevelNumber.
MultiLevelNumber = NewType("MultiLevelNumber", tuple[int, ...])

# An inclusive range of MultiLevelNumber.
MultiLevelRange = NewType(
    "MultiLevelRange", tuple[MultiLevelNumber, MultiLevelNumber]
)


def parse_number(number_str: str, /) -> MultiLevelNumber:
    """Returns a MultiLevelNumber parsed from a string."""
    if number_str == "all":
        return MultiLevelNumber(())
    if "-" in number_str:
        raise ValueError(
            "MultiLevelNumber cannot have negative components: "
            f"{number_str!r}"
        )
    try:
        return MultiLevelNumber(tuple(map(int, number_str.split("."))))
    except ValueError as parse_error:
        raise ValueError(
            f"Invalid MultiLevelNumber: {number_str!r}"
        ) from parse_error


def _parse_multi_level_range(range_str: str) -> MultiLevelRange:
    start_str, sep, end_str = range_str.partition("-")
    if not sep:
        end_str = start_str
    return MultiLevelRange(
        (
            parse_number(start_str.strip()),
            parse_number(end_str.strip()),
        )
    )


def _ge_start(number: MultiLevelNumber, *, start: MultiLevelNumber) -> bool:
    if len(number) >= len(start):
        return number[: len(start)] >= start
    else:
        return number > start[: len(number)]


def _le_end(number: MultiLevelNumber, *, end: MultiLevelNumber) -> bool:
    if len(number) >= len(end):
        return number[: len(end)] <= end
    else:
        return number < end[: len(number)]


class MultiLevelSet:
    """A set of MultiLevelNumber."""

    def __init__(self, ranges: Collection[MultiLevelRange]):
        self._ranges = ranges

    @classmethod
    def from_string(cls, set_str: str, /) -> Self:
        """Returns a set parsed from a string.

        Args:
            set_str: A comma-separated list of ranges. Each range can be of the
                form `a-b` where `a` and `b` are dotted numbers, `a` where `a`
                is a dotted number, or the literal string `all`. E.g.,
                "1-1.2,1.4-5" could represent seasons 1-5 except season 1
                episode 3.
        """
        if not set_str:
            return cls(())
        try:
            return cls(
                tuple(
                    _parse_multi_level_range(range_str)
                    for range_str in set_str.split(",")
                )
            )
        except ValueError as parse_error:
            raise ValueError(
                f"Invalid multi level set: {set_str!r}"
            ) from parse_error

    def __contains__(self, number: MultiLevelNumber) -> bool:
        for start, end in self._ranges:
            if _ge_start(number, start=start) and _le_end(number, end=end):
                return True
        return False
