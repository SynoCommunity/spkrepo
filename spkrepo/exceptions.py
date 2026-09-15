# -*- coding: utf-8 -*-
"""Domain exception types shared by parsing, signing, and validation."""


class SpkrepoError(Exception):
    """Base class for exceptions in spkrepo"""


class SPKParseError(SpkrepoError):
    """Exception raised when SPK parsing fails"""


class SPKSignError(SpkrepoError):
    """Exception raised when SPK signing fails"""
