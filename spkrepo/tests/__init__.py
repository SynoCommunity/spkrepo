# -*- coding: utf-8 -*-
from unittest import TestSuite, TextTestRunner

from spkrepo.tests import test_admin, test_api, test_frontend, test_nas, test_utils

# Test suite
suite = TestSuite(
    [
        test_admin.suite(),
        test_api.suite(),
        test_frontend.suite(),
        test_nas.suite(),
        test_utils.suite(),
    ]
)


if __name__ == "__main__":
    TextTestRunner().run(suite)
