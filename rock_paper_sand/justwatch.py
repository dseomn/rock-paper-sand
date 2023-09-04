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
"""Code that uses JustWatch's API.

There doesn't seem to be much documentation of the API, but
https://github.com/dawoudt/JustWatchAPI shows some ways it can be used. This
file does not use that library because 1) the library doesn't seem to add much
value over doing plain REST calls, so it's probably not worth the extra
dependency, and 2) the library doesn't give enough control over the HTTP calls
to enable useful things like caching and retrying specific errors.
"""

from typing import Any

import requests

_BASE_URL = "https://apis.justwatch.com/content"


class Api:
    """Wrapper around JustWatch's API."""

    def __init__(
        self,
        *,
        session: requests.Session,
        base_url: str = _BASE_URL,
    ):
        self._session = session
        self._base_url = base_url
        self._cache = {}

    def get(self, relative_url: str) -> Any:
        """Returns the decoded JSON response."""
        if relative_url in self._cache:
            return self._cache[relative_url]
        response = self._session.get(f"{self._base_url}/{relative_url}")
        response.raise_for_status()
        response_json = response.json()
        self._cache[relative_url] = response_json
        return response_json
