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

# pylint: disable=missing-module-docstring

from collections.abc import Collection, Mapping, Set
import datetime
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict
import requests

from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand import wikidata
from rock_paper_sand import wikidata_value
from rock_paper_sand.proto import config_pb2

_NOW = datetime.datetime.now(tz=datetime.timezone.utc)
_TIME_FORMAT = "+%Y-%m-%dT%H:%M:%SZ"
_TIME_IN_PAST_2 = (_NOW - datetime.timedelta(days=4)).strftime(_TIME_FORMAT)
_TIME_IN_PAST_1 = (_NOW - datetime.timedelta(days=2)).strftime(_TIME_FORMAT)
_TIME_IN_FUTURE_1 = (_NOW + datetime.timedelta(days=2)).strftime(_TIME_FORMAT)
_TIME_IN_FUTURE_2 = (_NOW + datetime.timedelta(days=4)).strftime(_TIME_FORMAT)


def _snak_item(item_id: str) -> Any:
    return {
        "snaktype": "value",
        "datatype": "wikibase-item",
        "datavalue": {
            "type": "wikibase-entityid",
            "value": {"entity-type": "item", "id": item_id},
        },
    }


def _snak_string(value: str) -> Any:
    return {
        "snaktype": "value",
        "datatype": "string",
        "datavalue": {"type": "string", "value": value},
    }


def _snak_time(time: str) -> Any:
    return {
        "snaktype": "value",
        "datatype": "time",
        "datavalue": {
            "type": "time",
            "value": {
                "calendarmodel": (
                    wikidata_value.Q_PROLEPTIC_GREGORIAN_CALENDAR.uri
                ),
                "timezone": 0,
                "before": 0,
                "after": 0,
                "precision": 11,  # day
                "time": time,
            },
        },
    }


def _sparql_item(item_id: str) -> Any:
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{item_id}"}


def _sparql_string(value: str) -> Any:
    return {"type": "literal", "value": value}


class WikidataSessionTest(parameterized.TestCase):
    @parameterized.parameters(False, True)
    def test_session(self, refresh: bool) -> None:
        # For now this is basicaly just a smoke test, because it's probably not
        # worth the effort to really test this function.
        self.enterContext(flagsaver.flagsaver(wikidata_refresh=refresh))
        with wikidata.requests_session() as session:
            self.assertIsInstance(session, requests.Session)


class WikidataApiTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_session = mock.create_autospec(
            requests.Session, spec_set=True, instance=True
        )
        self._api = wikidata.Api(session=self._mock_session)

    def test_entity(self) -> None:
        entity = wikidata_value.Entity(json_full={"foo": "bar"})
        self._mock_session.get.return_value.json.return_value = {
            "entities": {"Q1": entity.json_full}
        }

        first_response = self._api.entity(wikidata_value.ItemRef("Q1"))
        second_response = self._api.entity(wikidata_value.ItemRef("Q1"))

        self.assertEqual(entity, first_response)
        self.assertEqual(entity, second_response)
        self.assertSequenceEqual(
            (
                # Note that this only happens once because the second time is
                # cached.
                mock.call.get(
                    "https://www.wikidata.org/wiki/Special:EntityData/Q1.json"
                ),
                mock.call.get().raise_for_status(),
                mock.call.get().json(),
            ),
            self._mock_session.mock_calls,
        )

    def test_sparql(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {"bindings": [{"foo": "bar"}]}
        }

        results = self._api.sparql("SELECT ...")

        self.assertEqual([{"foo": "bar"}], results)
        self.assertSequenceEqual(
            (
                mock.call.get(
                    "https://query.wikidata.org/sparql",
                    params=[("query", "SELECT ...")],
                    headers={"Accept": "application/sparql-results+json"},
                ),
                mock.call.get().raise_for_status(),
                mock.call.get().json(),
            ),
            self._mock_session.mock_calls,
        )

    def test_entity_classes(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "entities": {
                "Q1": {
                    "claims": {
                        wikidata_value.P_INSTANCE_OF.id: [
                            {"rank": "normal", "mainsnak": _snak_item("Q2")},
                            {"rank": "normal", "mainsnak": _snak_item("Q3")},
                        ],
                    }
                }
            }
        }

        first_result = self._api.entity_classes(wikidata_value.ItemRef("Q1"))
        second_result = self._api.entity_classes(wikidata_value.ItemRef("Q1"))

        expected_classes = {
            wikidata_value.ItemRef("Q2"),
            wikidata_value.ItemRef("Q3"),
        }
        self.assertEqual(expected_classes, first_result)
        self.assertEqual(expected_classes, second_result)
        # Note that this only happens once because the second time is cached.
        self._mock_session.get.assert_called_once_with(
            "https://www.wikidata.org/wiki/Special:EntityData/Q1.json"
        )

    def test_forms_of_creative_work(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "entities": {
                "Q1": {
                    "claims": {
                        wikidata_value.P_FORM_OF_CREATIVE_WORK.id: [
                            {"rank": "normal", "mainsnak": _snak_item("Q2")},
                            {"rank": "normal", "mainsnak": _snak_item("Q3")},
                        ],
                    }
                }
            }
        }

        first_result = self._api.forms_of_creative_work(
            wikidata_value.ItemRef("Q1")
        )
        second_result = self._api.forms_of_creative_work(
            wikidata_value.ItemRef("Q1")
        )

        expected_forms = {
            wikidata_value.ItemRef("Q2"),
            wikidata_value.ItemRef("Q3"),
        }
        self.assertEqual(expected_forms, first_result)
        self.assertEqual(expected_forms, second_result)
        # Note that this only happens once because the second time is cached.
        self._mock_session.get.assert_called_once_with(
            "https://www.wikidata.org/wiki/Special:EntityData/Q1.json"
        )

    def test_transitive_subclasses(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {
                "bindings": [
                    {"class": _sparql_item("Q1")},
                    {"class": _sparql_item("Q2")},
                ]
            }
        }

        first_result = self._api.transitive_subclasses(
            wikidata_value.ItemRef("Q1")
        )
        second_result = self._api.transitive_subclasses(
            wikidata_value.ItemRef("Q1")
        )

        expected_subclasses = {
            wikidata_value.ItemRef("Q1"),
            wikidata_value.ItemRef("Q2"),
        }
        self.assertEqual(expected_subclasses, first_result)
        self.assertEqual(expected_subclasses, second_result)
        # Note that this only happens once because the second time is cached.
        self._mock_session.get.assert_called_once()

    @parameterized.named_parameters(
        dict(
            testcase_name="no_results",
            sparql_results=[],
            expected_result=dict(
                parents=(),
                siblings=(),
                children=(),
                loose=(),
            ),
            expected_cached_classes={},
        ),
        dict(
            testcase_name="with_results",
            sparql_results=[
                {
                    "item": _sparql_item("Q2"),
                    "relation": _sparql_string("parent"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q31"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q31"),
                },
                {
                    "item": _sparql_item("Q3"),
                    "relation": _sparql_string("sibling"),
                    "class": _sparql_item("Q32"),
                },
                {
                    "item": _sparql_item("Q4"),
                    "relation": _sparql_string("child"),
                },
                {
                    "item": _sparql_item("Q5"),
                    "relation": _sparql_string("child"),
                },
                {
                    "item": _sparql_item("Q4"),
                    "relation": _sparql_string("loose"),
                },
            ],
            expected_result=dict(
                parents=("Q2",),
                siblings=("Q3",),
                children=("Q4", "Q5"),
                loose=("Q4",),
            ),
            expected_cached_classes={
                "Q2": (),
                "Q3": ("Q31", "Q32"),
                "Q4": (),
                "Q5": (),
            },
        ),
    )
    def test_related_media(
        self,
        *,
        sparql_results: list[Any],
        expected_result: Mapping[str, Collection[str]],
        expected_cached_classes: Mapping[str, Collection[str]],
    ) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {"bindings": sparql_results}
        }

        first_result = self._api.related_media(wikidata_value.ItemRef("Q1"))
        second_result = self._api.related_media(wikidata_value.ItemRef("Q1"))
        actual_classes = {
            item_ref: self._api.entity_classes(item_ref)
            for item_ref in {
                *first_result.parents,
                *first_result.siblings,
                *first_result.children,
                *first_result.loose,
            }
        }

        expected_related_media = wikidata.RelatedMedia(
            **{
                key: frozenset(map(wikidata_value.ItemRef, values))
                for key, values in expected_result.items()
            }
        )
        expected_classes = {
            wikidata_value.ItemRef(item_id): frozenset(
                map(wikidata_value.ItemRef, classes)
            )
            for item_id, classes in expected_cached_classes.items()
        }
        self.assertEqual(expected_related_media, first_result)
        self.assertEqual(expected_related_media, second_result)
        self.assertEqual(expected_classes, actual_classes)
        # Note that this only happens once because the second related_media()
        # call and all the item_classes() calls are cached.
        self._mock_session.get.assert_called_once()

    def test_related_media_error(self) -> None:
        self._mock_session.get.return_value.json.return_value = {
            "results": {
                "bindings": [
                    {
                        "item": _sparql_item("Q2"),
                        "relation": _sparql_string("kumquat"),
                    }
                ]
            }
        }

        with self.assertRaisesRegex(ValueError, "kumquat"):
            self._api.related_media(wikidata_value.ItemRef("Q1"))


class WikidataFilterTest(parameterized.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._mock_api = mock.create_autospec(
            wikidata.Api, spec_set=True, instance=True
        )
        self._mock_api.transitive_subclasses.side_effect = lambda class_ref: {
            class_ref
        }

    @parameterized.named_parameters(
        dict(
            testcase_name="no_item_id",
            filter_config={},
            item={"name": "foo"},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="no_match_conditions",
            filter_config={},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={"Q1": {}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_no_match",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={"Q1": {"claims": {}}},
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="release_statuses_unknown",
            filter_config={"releaseStatuses": ["RELEASE_STATUS_UNSPECIFIED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={"Q1": {"claims": {}}},
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_range",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_2),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_start",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_in_range",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_start",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_end",
            filter_config={"releaseStatuses": ["ONGOING"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_range",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_START_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_2),
                            },
                        ],
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_end",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_END_TIME.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_before_release",
            filter_config={"releaseStatuses": ["UNRELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_PUBLICATION_DATE.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_FUTURE_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="release_statuses_after_release",
            filter_config={"releaseStatuses": ["RELEASED"]},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q1": {
                    "claims": {
                        wikidata_value.P_PUBLICATION_DATE.id: [
                            {
                                "rank": "normal",
                                "mainsnak": _snak_time(_TIME_IN_PAST_1),
                            },
                        ],
                    }
                }
            },
            expected_result=media_filter.FilterResult(True),
        ),
        dict(
            testcase_name="related_media_ignores_non_top_level",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            parent_fully_qualified_name="foo",
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="related_media_none",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(False),
        ),
        dict(
            testcase_name="related_media_not_loose",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q4"}],
            },
            api_entities={
                "Q2": {"labels": {}, "descriptions": {}},
                "Q3": {"labels": {}, "descriptions": {}},
                "Q5": {"labels": {}, "descriptions": {}},
            },
            api_entity_classes={
                "Q1": set(),
                "Q2": set(),
                "Q3": set(),
                "Q4": set(),
                "Q5": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.ItemRef("Q2"),
                        wikidata_value.ItemRef("Q3"),
                    },
                    loose=set(),
                ),
                "Q2": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q1")},
                    siblings={wikidata_value.ItemRef("Q3")},
                    children=set(),
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q1")},
                    siblings={
                        wikidata_value.ItemRef("Q2"),
                        wikidata_value.ItemRef("Q4"),
                    },
                    children=set(),
                    loose=set(),
                ),
                "Q4": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q5")},
                    siblings={wikidata_value.ItemRef("Q3")},
                    children=set(),
                    loose=set(),
                ),
                "Q5": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.ItemRef("Q4")},
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q2>"
                    ),
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q3>"
                    ),
                    # Q4 is in the config, so not shown here.
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q5>"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_loose",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q2"}],
            },
            api_entities={
                "Q3": {"labels": {}, "descriptions": {}},
            },
            api_entity_classes={
                "Q2": set(),
                "Q3": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    # Q2 is upgraded to non-loose, because it's also in the
                    # config.
                    loose={wikidata_value.ItemRef("Q2")},
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose={wikidata_value.ItemRef("Q3")},
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "loosely-related item: "
                        "<https://www.wikidata.org/wiki/Q3>"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_config_has_unrelated",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "parts": [{"name": "bar", "wikidata": "Q2"}],
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "item in config file that's not related to "
                        "https://www.wikidata.org/wiki/Q1: "
                        "https://www.wikidata.org/wiki/Q2"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_excludes_ignored_items",
            filter_config={"relatedMedia": {}},
            item={
                "name": "foo",
                "wikidata": "Q1",
                "wikidataIgnore": ["Q3", "Q4", "Q5"],
                "wikidataClassesIgnore": ["Q61"],
            },
            api_entity_classes={
                "Q1": set(),
                "Q2": {wikidata_value.Q_FICTIONAL_ENTITY},
                "Q3": set(),
                "Q4": set(),
                "Q6": {wikidata_value.ItemRef("Q61")},
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q4")},
                    siblings={wikidata_value.Q_PARATEXT},
                    children={wikidata_value.ItemRef("Q6")},
                    loose={
                        wikidata_value.ItemRef("Q2"),
                        wikidata_value.ItemRef("Q3"),
                    },
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "item configured to be ignored, but not found: "
                        "https://www.wikidata.org/wiki/Q5"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_ignores_integral_children",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q2": {"labels": {}, "descriptions": {}},
                "Q22": {"labels": {}, "descriptions": {}},
                "Q24": {
                    "claims": {
                        wikidata_value.P_PART_OF_THE_SERIES.id: [
                            {
                                "rank": "normal",
                                "qualifiers": {
                                    wikidata_value.P_SERIES_ORDINAL.id: [
                                        _snak_string("1"),
                                    ],
                                },
                            },
                        ],
                    },
                },
                "Q3": {"labels": {}, "descriptions": {}},
                "Q4": {"labels": {}, "descriptions": {}},
            },
            api_entity_classes={
                "Q1": set(),
                "Q2": {wikidata_value.Q_TELEVISION_SERIES},
                "Q21": {wikidata_value.Q_TELEVISION_SERIES_EPISODE},
                "Q22": {
                    wikidata_value.Q_TELEVISION_SERIES_EPISODE,
                    wikidata_value.Q_TELEVISION_SPECIAL,
                },
                "Q23": {wikidata_value.Q_TELEVISION_SERIES_SEASON},
                "Q24": {wikidata_value.Q_TELEVISION_PILOT},
                "Q31": {wikidata_value.Q_LITERARY_WORK},
                "Q3": {wikidata_value.Q_LITERARY_WORK},
                "Q4": {wikidata_value.Q_FILM},
                "Q41": {wikidata_value.Q_RELEASE_GROUP},
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.ItemRef("Q2"),
                        wikidata_value.ItemRef("Q31"),
                        wikidata_value.ItemRef("Q4"),
                    },
                    loose=set(),
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.ItemRef("Q21"),
                        wikidata_value.ItemRef("Q22"),
                        wikidata_value.ItemRef("Q23"),
                        wikidata_value.ItemRef("Q24"),
                    },
                    loose=set(),
                ),
                "Q21": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q22": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q23": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q24": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q31": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q3")},
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q4": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.ItemRef("Q41")},
                    loose=set(),
                ),
                "Q41": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q2>"
                    ),
                    # Q21 is an integral child of Q2.
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q22>"
                    ),
                    # Q23 is an integral child of Q2.
                    # Q24 is an integral child of Q2.
                    # Q31 is an integral child of Q3.
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q3>"
                    ),
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q4>"
                    ),
                    # Q41 is an integral child of Q4.
                },
            ),
        ),
        dict(
            testcase_name="related_media_does_not_ignore_special_tv_pilots",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q2": {"labels": {}, "descriptions": {}, "claims": {}},
                "Q3": {
                    "labels": {},
                    "descriptions": {},
                    "claims": {
                        wikidata_value.P_PART_OF_THE_SERIES.id: [
                            {
                                "rank": "normal",
                                "qualifiers": {
                                    wikidata_value.P_SERIES_ORDINAL.id: [
                                        _snak_string("0"),
                                        _snak_string("1"),
                                    ],
                                },
                            },
                        ],
                    },
                },
                "Q4": {
                    "labels": {},
                    "descriptions": {},
                    "claims": {
                        wikidata_value.P_PART_OF_THE_SERIES.id: [
                            {
                                "rank": "normal",
                                "qualifiers": {
                                    wikidata_value.P_SERIES_ORDINAL.id: [
                                        _snak_string("1.5"),
                                    ],
                                },
                            },
                        ],
                    },
                },
            },
            api_entity_classes={
                "Q1": {wikidata_value.Q_TELEVISION_SERIES},
                "Q2": {wikidata_value.Q_TELEVISION_PILOT},
                "Q3": {wikidata_value.Q_TELEVISION_PILOT},
                "Q4": {wikidata_value.Q_TELEVISION_PILOT},
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={
                        wikidata_value.ItemRef("Q2"),
                        wikidata_value.ItemRef("Q3"),
                        wikidata_value.ItemRef("Q4"),
                    },
                    loose=set(),
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
                "Q4": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q2>"
                    ),
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q3>"
                    ),
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q4>"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_does_not_traverse_collections",
            filter_config={"relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q3": {"labels": {}, "descriptions": {}},
            },
            api_entity_classes={
                "Q1": set(),
                "Q2": {wikidata_value.Q_ANTHOLOGY},
                "Q3": {wikidata_value.Q_ANTHOLOGY},
                "Q4": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents={wikidata_value.ItemRef("Q2")},
                    siblings=set(),
                    children={wikidata_value.ItemRef("Q3")},
                    loose=set(),
                ),
                "Q3": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children={wikidata_value.ItemRef("Q4")},
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: <https://www.wikidata.org/wiki/Q3>"
                    ),
                },
            ),
        ),
        dict(
            testcase_name="related_media_includes_label_and_description",
            filter_config={"languages": ["en"], "relatedMedia": {}},
            item={"name": "foo", "wikidata": "Q1"},
            api_entities={
                "Q2": {
                    "labels": {"en": {"value": "film 2"}},
                    "descriptions": {"en": {"value": "2002 film"}},
                },
                "Q3": {
                    "labels": {"en": {"value": "film 3"}},
                    "descriptions": {"en": {"value": "2003 film"}},
                },
            },
            api_entity_classes={
                "Q2": set(),
                "Q3": set(),
            },
            api_related_media={
                "Q1": wikidata.RelatedMedia(
                    parents=set(),
                    siblings={wikidata_value.ItemRef("Q2")},
                    children=set(),
                    loose={wikidata_value.ItemRef("Q3")},
                ),
                "Q2": wikidata.RelatedMedia(
                    parents=set(),
                    siblings=set(),
                    children=set(),
                    loose=set(),
                ),
            },
            expected_result=media_filter.FilterResult(
                True,
                extra={
                    media_filter.ResultExtraString(
                        "related item: film 2 (2002 film) "
                        "<https://www.wikidata.org/wiki/Q2>"
                    ),
                    media_filter.ResultExtraString(
                        "loosely-related item: film 3 (2003 film) "
                        "<https://www.wikidata.org/wiki/Q3>"
                    ),
                },
            ),
        ),
    )
    def test_filter(
        self,
        *,
        filter_config: Any,
        item: Any,
        parent_fully_qualified_name: str | None = None,
        api_entities: Mapping[str, Any] = immutabledict.immutabledict(),
        api_entity_classes: Mapping[str, Set[wikidata_value.ItemRef]] = (
            immutabledict.immutabledict()
        ),
        api_related_media: Mapping[str, wikidata.RelatedMedia] = (
            immutabledict.immutabledict()
        ),
        expected_result: media_filter.FilterResult,
    ) -> None:
        self._mock_api.entity.side_effect = (
            lambda entity_ref: wikidata_value.Entity(
                json_full=api_entities[entity_ref.id]
            )
        )
        self._mock_api.entity_classes.side_effect = (
            lambda entity_ref: api_entity_classes[entity_ref.id]
        )
        self._mock_api.related_media.side_effect = (
            lambda item_ref: api_related_media[item_ref.id]
        )
        test_filter = wikidata.Filter(
            json_format.ParseDict(filter_config, config_pb2.WikidataFilter()),
            api=self._mock_api,
        )

        result = test_filter.filter(
            media_filter.FilterRequest(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(item, config_pb2.MediaItem()),
                    parent_fully_qualified_name=parent_fully_qualified_name,
                )
            )
        )

        self.assertEqual(expected_result, result)

    def test_too_many_related_items(self) -> None:
        self._mock_api.entity_classes.return_value = set()
        self._mock_api.related_media.return_value = wikidata.RelatedMedia(
            parents=set(),
            siblings={wikidata_value.ItemRef(f"Q{n}") for n in range(1001)},
            children=set(),
            loose=set(),
        )
        test_filter = wikidata.Filter(
            json_format.ParseDict(
                {"relatedMedia": {}}, config_pb2.WikidataFilter()
            ),
            api=self._mock_api,
        )
        request = media_filter.FilterRequest(
            media_item.MediaItem.from_config(
                json_format.ParseDict(
                    {"name": "foo", "wikidata": "Q99999"},
                    config_pb2.MediaItem(),
                )
            )
        )

        with self.assertRaisesRegex(ValueError, "Too many related media items"):
            test_filter.filter(request)


if __name__ == "__main__":
    absltest.main()
