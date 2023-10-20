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
"""Code that uses Wikidata's APIs."""

from collections.abc import Generator, Sequence
import contextlib
import enum
from typing import Any

import requests
import requests_cache

from rock_paper_sand import network


class _Property(enum.Enum):
    PUBLICATION_DATE = "P577"
    DATE_OF_FIRST_PERFORMANCE = "P1191"
    START_TIME = "P580"
    END_TIME = "P582"


@contextlib.contextmanager
def requests_session() -> Generator[requests.Session, None, None]:
    """Returns a context manager for a session for Wikidata APIs."""
    with requests_cache.CachedSession(
        **network.requests_cache_defaults(),
    ) as session:
        network.configure_session(session)
        yield session


def _truthy_statements(item: Any, prop: _Property) -> Sequence[Any]:
    # https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format#Truthy_statements
    statements = item["claims"].get(prop.value, ())
    return tuple(
        statement
        for statement in statements
        if statement["rank"] == "preferred"
    ) or tuple(
        statement for statement in statements if statement["rank"] == "normal"
    )


class Api:
    """Wrapper around Wikidata APIs."""

    def __init__(
        self,
        *,
        session: requests.Session,
    ) -> None:
        self._session = session
        self._item_by_qid: dict[str, Any] = {}

    def item(self, qid: str) -> Any:
        """Returns an item in full JSON format."""
        if qid not in self._item_by_qid:
            response = self._session.get(
                f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
            )
            response.raise_for_status()
            self._item_by_qid[qid] = response.json()["entities"][qid]
        return self._item_by_qid[qid]
