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

from collections.abc import Collection
import datetime
import importlib.metadata
import os.path
from typing import Any

import requests
import requests.adapters
import requests_cache
import urllib3.util

from rock_paper_sand import flags_and_constants


def _user_agent() -> str:
    parts = ["rock-paper-sand/0", "(https://github.com/dseomn/rock-paper-sand)"]
    for package in ("requests", "requests-cache", "urllib3"):
        parts.append(f"{package}/{importlib.metadata.version(package)}")
    return " ".join(parts)


def requests_cache_defaults() -> dict[str, Any]:
    """Returns default kwargs for requests_cache.CachedSession."""
    # TODO(requests-cache >= 1.0.0): Delete old cache entries using the
    # older_than parameter.
    return dict(
        backend=requests_cache.SQLiteCache(
            db_path=os.path.join(
                flags_and_constants.CACHE_DIR.value,
                "requests-cache",
                "cache.sqlite",
            ),
            serializer="json",
        ),
        expire_after=datetime.timedelta(minutes=5),
        cache_control=True,
    )


def requests_http_adapter(
    *,
    additional_retry_methods: Collection[str] = (),
) -> requests.adapters.HTTPAdapter:
    """Returns an HTTPAdapter for requests.

    Args:
        additional_retry_methods: Methods other than the defaults to retry on.
    """
    return requests.adapters.HTTPAdapter(
        max_retries=urllib3.util.Retry(
            allowed_methods={
                *urllib3.util.Retry.DEFAULT_ALLOWED_METHODS,
                *additional_retry_methods,
            },
            status_forcelist=urllib3.util.Retry.RETRY_AFTER_STATUS_CODES,
            backoff_factor=0.1,
        ),
    )


def configure_session(
    session: requests.Session,
    *,
    additional_retry_methods: Collection[str] = (),
) -> None:
    """Configures a session with some defaults.

    Args:
        session: Session to configure.
        additional_retry_methods: See requests_http_adapter().
    """
    http_adapter = requests_http_adapter(
        additional_retry_methods=additional_retry_methods,
    )
    session.mount("http://", http_adapter)
    session.mount("https://", http_adapter)
    session.headers["User-Agent"] = _user_agent()


def null_requests_session() -> requests.Session:
    """Returns a requests session that can't do anything, mainly for testing."""
    session = requests.session()
    session.close()
    session.adapters.clear()
    return session
