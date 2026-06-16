# -*- coding: utf-8 -*-
from spkrepo.filters import abbreviate_number, is_hidden_field, sort_fields


class TestIsHiddenField:
    def test_hidden_field(self):
        from wtforms import Form, HiddenField

        class F(Form):
            f = HiddenField()

        assert is_hidden_field(F().f) is True

    def test_non_hidden_field(self):
        from wtforms import Form, StringField

        class F(Form):
            f = StringField()

        assert is_hidden_field(F().f) is False


class TestSortFields:
    def test_sort_fields_with_some_matching(self):
        from wtforms import Form, StringField

        class F(Form):
            a = StringField()
            b = StringField()
            c = StringField()

        form = F()
        result = sort_fields(form, field_names=["c", "a"])
        assert [f.name for f in result] == ["c", "a", "b"]

    def test_sort_fields_with_no_matches(self):
        from wtforms import Form, StringField

        class F(Form):
            a = StringField()
            b = StringField()

        form = F()
        result = sort_fields(form, field_names=["z"])
        assert [f.name for f in result] == ["a", "b"]

    def test_sort_fields_with_none_field_names(self):
        from wtforms import Form, StringField

        class F(Form):
            a = StringField()
            b = StringField()

        form = F()
        result = sort_fields(form)
        assert [f.name for f in result] == ["a", "b"]

    def test_sort_fields_with_empty_field_names(self):
        from wtforms import Form, StringField

        class F(Form):
            a = StringField()
            b = StringField()

        form = F()
        result = sort_fields(form, field_names=[])
        assert [f.name for f in result] == ["a", "b"]


class TestAbbreviateNumber:
    def test_none(self):
        assert abbreviate_number(None) == "0"

    def test_zero(self):
        assert abbreviate_number(0) == "0"

    def test_small_numbers(self):
        assert abbreviate_number(1) == "1"
        assert abbreviate_number(500) == "500"
        assert abbreviate_number(999) == "999"

    def test_thousands(self):
        assert abbreviate_number(1000) == "1K"
        assert abbreviate_number(1005) == "1K"
        assert abbreviate_number(10500) == "10.5K"
        assert abbreviate_number(103897) == "103.9K"
        assert abbreviate_number(999999) == "1M"

    def test_millions(self):
        assert abbreviate_number(1000000) == "1M"
        assert abbreviate_number(1500000) == "1.5M"
        assert abbreviate_number(10000000) == "10M"
        assert abbreviate_number(123456789) == "123.5M"

    def test_negative_values(self):
        assert abbreviate_number(-500) == "-500"
        assert abbreviate_number(-1500) == "-1.5K"

    def test_string_input(self):
        assert abbreviate_number("abc") == "abc"

    def test_float_input(self):
        assert abbreviate_number(1500.5) == "1.5K"
