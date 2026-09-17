# -*- coding: utf-8 -*-
"""Reference-data seed: architectures, firmware, languages, roles, services."""

from ..ext import db
from ..models import Architecture, Firmware, Language, Role, Service


def populate_reference_data():
    """Insert the reference rows: architectures, firmware, languages, roles,
    services."""
    db.session.execute(
        Architecture.__table__.insert().values(
            [
                {"code": "noarch"},
                {"code": "cedarview"},
                {"code": "88f628x"},
                {"code": "qoriq"},
            ]
        )
    )
    db.session.execute(
        Firmware.__table__.insert().values(
            [
                {"version": "3.1", "build": 1594, "type": "dsm"},
                {"version": "5.0", "build": 4458, "type": "dsm"},
                {"version": "6.2", "build": 23739, "type": "dsm"},
                {"version": "7.1", "build": 42661, "type": "dsm"},
            ]
        )
    )
    db.session.execute(
        Language.__table__.insert().values(
            [{"code": "enu", "name": "English"}, {"code": "fre", "name": "French"}]
        )
    )
    db.session.execute(
        Role.__table__.insert().values(
            [
                {"name": "admin", "description": "Administrator"},
                {"name": "package_admin", "description": "Package Administrator"},
                {"name": "developer", "description": "Developer"},
            ]
        )
    )
    db.session.execute(
        Service.__table__.insert().values([{"code": "apache-web"}, {"code": "mysql"}])
    )
