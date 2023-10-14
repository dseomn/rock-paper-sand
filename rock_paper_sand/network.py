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
"""Utilities for accessing network resources."""

import requests
import requests.adapters
import urllib3.util


def requests_http_adapter() -> requests.adapters.HTTPAdapter:
    """Returns an HTTPAdapter for requests."""
    return requests.adapters.HTTPAdapter(
        max_retries=urllib3.util.Retry(
            status_forcelist=urllib3.util.Retry.RETRY_AFTER_STATUS_CODES,
            backoff_factor=0.1,
        ),
    )


def configure_session(session: requests.Session) -> None:
    """Configures a session with some defaults."""
    http_adapter = requests_http_adapter()
    session.mount("http://", http_adapter)
    session.mount("https://", http_adapter)
    session.headers[
        "User-Agent"
    ] = "rock_paper_sand/0 https://github.com/dseomn/rock-paper-sand"


def null_requests_session() -> requests.Session:
    """Returns a requests session that can't do anything, mainly for testing."""
    session = requests.session()
    session.close()
    session.adapters.clear()
    return session
