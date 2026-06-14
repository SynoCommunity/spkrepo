# -*- coding: utf-8 -*-
from wtforms import HiddenField


def is_hidden_field(field):
    """Return True if the given WTForms field is a hidden field."""
    return isinstance(field, HiddenField)


def sort_fields(form, field_names=None):
    """
    Return form fields in the order specified by field_names, with any
    remaining fields appended in their original order.
    """
    field_names = field_names or []
    fields = []
    for field in form:
        if field.name in field_names:
            fields.insert(field_names.index(field.name), field)
        else:
            fields.append(field)
    return fields


def abbreviate_number(value):
    """Abbreviate large numbers with K/M suffixes (e.g. 103897 -> 103.9K)."""
    if value is None:
        return "0"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(value) >= 1_000_000:
        result = f"{value / 1_000_000:.1f}M"
        return result.replace(".0M", "M")
    if abs(value) >= 1_000:
        result = f"{value / 1_000:.1f}K"
        result = result.replace(".0K", "K")
        return "1M" if result == "1000K" else result
    return f"{value:,}"


def register_filters(app):
    """Register all Jinja2 template filters on the given Flask app."""
    app.template_filter()(is_hidden_field)
    app.template_filter()(sort_fields)
    app.template_filter()(abbreviate_number)
