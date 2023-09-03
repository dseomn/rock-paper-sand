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

import os.path

import cachecontrol
from cachecontrol.caches import file_cache
import requests
import urllib3.util

from rock_paper_sand import config


def requests_session() -> requests.Session:
    """Returns a requests session."""
    session = requests.session()
    http_adapter = cachecontrol.CacheControlAdapter(
        cache=file_cache.FileCache(
            directory=os.path.join(config.CACHE_DIR.value, "cachecontrol")
        ),
        max_retries=urllib3.util.Retry(
            status_forcelist=urllib3.util.Retry.RETRY_AFTER_STATUS_CODES,
            backoff_factor=0.1,
        ),
    )
    session.mount("http://", http_adapter)
    session.mount("https://", http_adapter)
    # TODO(dseomn): Add GitHub URL?
    session.headers["User-Agent"] = "rock_paper_sand/0"
    return session
