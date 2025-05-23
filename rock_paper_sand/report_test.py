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

from collections.abc import Sequence, Set
import copy
import email.parser
import email.policy
import json
import subprocess
import textwrap
import typing
from typing import Any
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from google.protobuf import json_format
import immutabledict

from rock_paper_sand import media_filter
from rock_paper_sand import media_item
from rock_paper_sand import report
from rock_paper_sand.proto import config_pb2
from rock_paper_sand.proto import state_pb2


class _ExtraInfoFilter(media_filter.Filter):
    def __init__(self, extra: Set[media_filter.ResultExtra]) -> None:
        self._extra = extra

    def filter(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        return media_filter.FilterResult(True, extra=self._extra)


class _FirstWordIsNotNo(media_filter.Filter):
    def valid_extra_keys(self) -> Set[str]:
        """See base class."""
        return {"first_word"}

    def filter(
        self, request: media_filter.FilterRequest
    ) -> media_filter.FilterResult:
        """See base class."""
        first_word, _, _ = request.item.proto.name.partition(" ")
        return media_filter.FilterResult(
            first_word != "no",
            extra={
                media_filter.ResultExtra(
                    data=immutabledict.immutabledict(first_word=first_word)
                )
            },
        )


class ReportTest(parameterized.TestCase):
    @parameterized.named_parameters(
        dict(
            testcase_name="section_missing_name",
            report_config={
                "sections": [
                    {"filter": {"all": {}}},
                ],
            },
            error_regex="name field is required",
            error_notes=("In sections[0] with name ''.",),
        ),
        dict(
            testcase_name="section_duplicate_name",
            report_config={
                "sections": [
                    {"name": "foo", "filter": {"all": {}}},
                    {"name": "foo", "filter": {"all": {}}},
                ],
            },
            error_regex="name field must be unique",
            error_notes=("In sections[1] with name 'foo'.",),
        ),
        dict(
            testcase_name="group_by_missing_key",
            report_config={
                "sections": [
                    {"name": "foo", "filter": {"all": {}}, "groupBy": {}},
                ],
            },
            error_regex="key field is required",
            error_notes=("In sections[0] with name 'foo'.",),
        ),
        dict(
            testcase_name="group_by_invalid_key",
            report_config={
                "sections": [
                    {
                        "name": "foo",
                        "filter": {"all": {}},
                        "groupBy": {"key": "kumquat"},
                    },
                ],
            },
            error_regex="Group key 'kumquat' is not a valid key",
            error_notes=("In sections[0] with name 'foo'.",),
        ),
    )
    def test_invalid_config(
        self,
        *,
        report_config: Any,
        error_regex: str,
        error_notes: Sequence[str],
    ) -> None:
        with self.assertRaisesRegex(ValueError, error_regex) as error:
            report.Report(
                json_format.ParseDict(report_config, config_pb2.Report()),
                filter_registry=media_filter.Registry(),
            )
        self.assertSequenceEqual(error_notes, error.exception.__notes__)

    @parameterized.named_parameters(
        dict(
            testcase_name="simple",
            report_config={
                "sections": [
                    {"name": "all", "filter": {"all": {}}},
                    {"name": "none", "filter": {"not": {"all": {}}}},
                ]
            },
            media=[
                {
                    "name": "foo",
                    "comment": "FOO!",
                    "customData": {"a": "b"},
                    "done": "all",
                    "wikidata": "Q1",
                    "justwatch": "jw",
                },
                {"name": "bar", "parts": [{"name": "quux"}]},
            ],
            expected_result={
                "all": [
                    {
                        "name": "foo",
                        "comment": "FOO!",
                        "customData": {"a": "b"},
                        "done": "all",
                        "wikidata": "Q1",
                        "justwatch": "jw",
                    },
                    {"name": "bar", "parts": [{"name": "quux"}]},
                ],
                "none": [],
            },
        ),
        dict(
            testcase_name="with_extra",
            report_config={
                "sections": [
                    {
                        "name": "extra",
                        "filter": {
                            "or": {
                                "filters": [
                                    {"ref": "extra-without-str"},
                                    {"ref": "extra-with-str"},
                                ]
                            }
                        },
                    }
                ]
            },
            media=[{"name": "foo"}],
            expected_result={
                "extra": [
                    {"name": "foo", "extraInformation": ["example extra info"]},
                ],
            },
        ),
        dict(
            testcase_name="partial_match",
            report_config={
                "sections": [
                    {
                        "name": "custom_availability",
                        "filter": {"customAvailability": {"empty": False}},
                    },
                ]
            },
            media=[
                {
                    "name": "unmatched_parent",
                    "parts": [
                        {"name": "matched_child", "customAvailability": "yes"},
                        {"name": "unmatched_child"},
                    ],
                },
                {
                    "name": "matched_parent",
                    "customAvailability": "yes",
                    "parts": [
                        {"name": "matched_child", "customAvailability": "yes"},
                        {"name": "unmatched_child"},
                    ],
                },
            ],
            expected_result={
                "custom_availability": [
                    {
                        "name": "unmatched_parent",
                        "extraInformation": [
                            "parent did not match, but children did",
                        ],
                        "parts": [
                            {
                                "name": "matched_child",
                                "customAvailability": "yes",
                            },
                            "unmatched part: unmatched_child",
                        ],
                    },
                    {
                        "name": "matched_parent",
                        "customAvailability": "yes",
                        "parts": [
                            {
                                "name": "matched_child",
                                "customAvailability": "yes",
                            },
                            "unmatched part: unmatched_child",
                        ],
                    },
                ],
            },
        ),
        dict(
            testcase_name="group_by",
            report_config={
                "sections": [
                    {
                        "name": "grouped",
                        "filter": {"ref": "first-word-is-not-no"},
                        "groupBy": {"key": "first_word"},
                    }
                ]
            },
            media=[
                {"name": "foo"},
                {"name": "foo and other words"},
                {
                    "name": "no this is not included",
                    "parts": [{"name": "but this is"}],
                },
            ],
            expected_result={
                "grouped": {
                    "but": [
                        "no this is not included: but this is",
                    ],
                    "foo": [
                        "foo",
                        "foo and other words",
                    ],
                },
            },
        ),
    )
    def test_report_generate(
        self,
        report_config: Any,
        media: Any,
        expected_result: Any,
    ) -> None:
        filter_registry = media_filter.Registry()
        filter_registry.register(
            "extra-without-str",
            _ExtraInfoFilter(
                {
                    media_filter.ResultExtra(
                        data=immutabledict.immutabledict(test="no-str")
                    )
                }
            ),
        )
        filter_registry.register(
            "extra-with-str",
            _ExtraInfoFilter(
                {media_filter.ResultExtra(human_readable="example extra info")}
            ),
        )
        filter_registry.register("first-word-is-not-no", _FirstWordIsNotNo())
        report_ = report.Report(
            json_format.ParseDict(report_config, config_pb2.Report()),
            filter_registry=filter_registry,
        )
        result = report_.generate(
            tuple(
                media_item.MediaItem.from_config(
                    json_format.ParseDict(item, config_pb2.MediaItem())
                )
                for item in media
            )
        )
        self.assertEqual(expected_result, result)

    @parameterized.named_parameters(
        dict(
            testcase_name="not_configured",
            report_config={"name": "foo"},
            previous_results={"section-name": "foo"},
            current_results={"section-name": "bar"},
        ),
        dict(
            testcase_name="no_changes",
            report_config={
                "name": "foo",
                "emailHeaders": {"To": "alice@example.com"},
            },
            previous_results={"section-name": "foo"},
            current_results={"section-name": "foo"},
        ),
    )
    def test_report_notify_noop(
        self,
        *,
        report_config: Any,
        previous_results: Any,
        current_results: Any,
    ) -> None:
        report_ = report.Report(
            json_format.ParseDict(report_config, config_pb2.Report()),
            filter_registry=media_filter.Registry(),
        )
        actual_state = state_pb2.ReportState(
            previous_results_by_section_name={
                k: json.dumps(v) for k, v in previous_results.items()
            }
        )
        expected_state = copy.deepcopy(actual_state)
        mock_subprocess_run = mock.create_autospec(
            subprocess.run, spec_set=True
        )

        report_.notify(
            current_results,
            subprocess_run=mock_subprocess_run,
            report_state=actual_state,
        )

        mock_subprocess_run.assert_not_called()
        self.assertEqual(expected_state, actual_state)

    @parameterized.named_parameters(
        dict(
            testcase_name="partial_changes",
            previous_results={"unchanged": ["foo"], "changed": ["foo"]},
            current_results={"unchanged": ["foo"], "changed": ["not-foo"]},
            expected_diff_types="full",
            expected_message_parts=(
                (
                    "changed.diff",
                    textwrap.dedent(
                        """\
                        --- changed.yaml.old
                        +++ changed.yaml
                        @@ -1 +1 @@
                        -- foo
                        +- not-foo
                        """
                    ),
                ),
                ("unchanged.yaml", "- foo\n"),
                ("changed.yaml", "- not-foo\n"),
            ),
        ),
        dict(
            testcase_name="collapse_diff",
            previous_results={"collapse": ["foo"]},
            current_results={"collapse": ["not-foo"]},
            expected_diff_types="collapsed",
            expected_message_parts=(
                ("collapse.diff", "Section collapse differs\n"),
                ("collapse.yaml", "- not-foo\n"),
            ),
        ),
        dict(
            testcase_name="new_section",
            previous_results={},
            current_results={"foo": ["bar"]},
            expected_diff_types="created",
            expected_message_parts=(
                ("foo.diff", "Section foo is newly created\n"),
                ("foo.yaml", "- bar\n"),
            ),
        ),
        dict(
            testcase_name="deleted_section",
            previous_results={"foo": ["bar"]},
            current_results={},
            expected_diff_types="deleted",
            expected_message_parts=(("foo.diff", "Section foo was deleted\n"),),
        ),
    )
    def test_report_notify(
        self,
        *,
        previous_results: Any,
        current_results: Any,
        expected_diff_types: str,
        expected_message_parts: Any,
    ) -> None:
        report_ = report.Report(
            json_format.ParseDict(
                {
                    "name": "some-report-name",
                    "emailHeaders": {"To": "alice@example.com"},
                    "emailBody": "some-email-body",
                    "sections": [
                        {
                            "name": name,
                            "collapseDiff": name == "collapse",
                            "filter": {"all": {}},
                        }
                        for name in current_results
                    ],
                },
                config_pb2.Report(),
            ),
            filter_registry=media_filter.Registry(),
        )
        report_state = state_pb2.ReportState(
            previous_results_by_section_name={
                k: json.dumps(v) for k, v in previous_results.items()
            }
        )
        mock_subprocess_run = mock.create_autospec(
            subprocess.run, spec_set=True
        )

        report_.notify(
            current_results,
            subprocess_run=mock_subprocess_run,
            report_state=report_state,
        )

        mock_subprocess_run.assert_called_once_with(
            ("/usr/sbin/sendmail", "-i", "-t"),
            check=True,
            input=mock.ANY,
        )
        message = typing.cast(
            email.message.EmailMessage,
            email.parser.BytesParser(
                # TODO(https://github.com/python/typeshed/issues/13531): Remove
                # type ignore.
                policy=email.policy.default  # type: ignore[arg-type]
            ).parsebytes(mock_subprocess_run.mock_calls[0].kwargs["input"]),
        )
        self.assertIn("some-report-name", message["Subject"])
        self.assertEqual("alice@example.com", message["To"])
        self.assertEqual(
            "some-report-name", message["Rock-Paper-Sand-Report-Name"]
        )
        self.assertEqual(
            expected_diff_types, message["Rock-Paper-Sand-Diff-Types"]
        )
        self.assertEqual("multipart/mixed", message.get_content_type())
        self.assertSequenceEqual(
            (
                (None, "some-email-body\n"),
                *expected_message_parts,
            ),
            tuple(
                (part.get_filename(), part.get_content())
                for part in message.iter_parts()
            ),
        )
        self.assertEqual(
            state_pb2.ReportState(
                previous_results_by_section_name={
                    k: json.dumps(v) for k, v in current_results.items()
                }
            ),
            report_state,
        )


if __name__ == "__main__":
    absltest.main()
