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

from absl.testing import absltest
from absl.testing import parameterized

from rock_paper_sand import multi_level_set


class MultiLevelSetTest(parameterized.TestCase):
    @parameterized.parameters(
        ("all", ()),
        ("1", (1,)),
        ("1.2", (1, 2)),
    )
    def test_parse_number_valid(
        self,
        number_str: str,
        number: tuple[int, ...],
    ) -> None:
        self.assertEqual(number, multi_level_set.parse_number(number_str))

    @parameterized.parameters(
        "",
        ".",
        "foo",
        "1..2",
        ".1",
        "1.",
        "1.-2",
    )
    def test_parse_number_invalid(self, number_str: str) -> None:
        with self.assertRaisesRegex(ValueError, "MultiLevelNumber"):
            multi_level_set.parse_number(number_str)

    @parameterized.named_parameters(
        dict(
            testcase_name="trivial_member",
            set_str="1.2.3",
            number=(1, 2, 3),
            is_member=True,
        ),
        dict(
            testcase_name="trivial_not_member",
            set_str="1.2.3",
            number=(4,),
            is_member=False,
        ),
        dict(
            testcase_name="parent_not_member",
            set_str="1.2.3",
            number=(1, 2),
            is_member=False,
        ),
        dict(
            testcase_name="child_member",
            set_str="1.2.3",
            number=(1, 2, 3, 4),
            is_member=True,
        ),
        dict(
            testcase_name="all",
            set_str="all",
            number=(1, 2, 3),
            is_member=True,
        ),
        dict(
            testcase_name="all_contains_all",
            set_str="all",
            number=(),
            is_member=True,
        ),
        dict(
            testcase_name="all_with_extra",
            set_str="1.2.3, all",
            number=(4, 5, 6),
            is_member=True,
        ),
        dict(
            testcase_name="empty",
            set_str="",
            number=(1, 2, 3),
            is_member=False,
        ),
        dict(
            testcase_name="before_range_shorter_close",
            set_str="1.2 - 2",
            number=(1,),
            is_member=False,
        ),
        dict(
            testcase_name="before_range_shorter",
            set_str="2.2 - 3",
            number=(1,),
            is_member=False,
        ),
        dict(
            testcase_name="before_range_same_length",
            set_str="2 - 3",
            number=(1,),
            is_member=False,
        ),
        dict(
            testcase_name="before_range_longer",
            set_str="2 - 3",
            number=(1, 2),
            is_member=False,
        ),
        dict(
            testcase_name="in_range_first",
            set_str="1 - 2",
            number=(1,),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_child_of_first",
            set_str="1 - 2",
            number=(1, 1),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_middle",
            set_str="1 - 3",
            number=(2,),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_child_of_middle",
            set_str="1 - 3",
            number=(2, 1),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_parent_of_middle",
            set_str="1.2 - 3.1",
            number=(2,),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_last",
            set_str="1 - 2",
            number=(2,),
            is_member=True,
        ),
        dict(
            testcase_name="in_range_child_of_last",
            set_str="1 - 2",
            number=(2, 3),
            is_member=True,
        ),
        dict(
            testcase_name="after_range_shorter_close",
            set_str="1 - 2.2",
            number=(2,),
            is_member=False,
        ),
        dict(
            testcase_name="after_range_shorter",
            set_str="1 - 2.2",
            number=(3,),
            is_member=False,
        ),
        dict(
            testcase_name="after_range_same_length",
            set_str="1 - 2",
            number=(3,),
            is_member=False,
        ),
        dict(
            testcase_name="after_range_longer",
            set_str="1 - 2",
            number=(3, 4),
            is_member=False,
        ),
        dict(
            testcase_name="gap",
            set_str="1 - 1.2, 1.4 - 1",
            number=(1, 3),
            is_member=False,
        ),
    )
    def test_valid_set(
        self,
        *,
        set_str: str,
        number: tuple[int, ...],
        is_member: bool,
    ) -> None:
        test_set = multi_level_set.MultiLevelSet.from_string(set_str)
        self.assertEqual(
            is_member, multi_level_set.MultiLevelNumber(number) in test_set
        )

    @parameterized.parameters(
        ".",
        "-",
        ",",
        "foo",
        "foo.bar",
        "foo-bar",
        "foo,bar",
        "1..2",
        ".1",
        "1.",
        "1--2",
        "-1",
        "1-",
        "1,,2",
        ",1",
        "1,",
    )
    def test_invalid_set(self, set_str: str) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid multi level set"):
            multi_level_set.MultiLevelSet.from_string(set_str)


if __name__ == "__main__":
    absltest.main()
