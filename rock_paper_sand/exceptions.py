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
"""Utilities for exceptions."""

from collections.abc import Generator
import contextlib


@contextlib.contextmanager
def add_note(note: str) -> Generator[None, None, None]:
    """Adds a note to any exceptions raised within the context."""
    try:
        yield
    except Exception as e:
        e.add_note(note)
        raise
