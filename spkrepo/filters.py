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


def register_filters(app):
    """Register all Jinja2 template filters on the given Flask app."""
    app.template_filter()(is_hidden_field)
    app.template_filter()(sort_fields)
