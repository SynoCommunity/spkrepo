# -*- coding: utf-8 -*-
class SpkrepoError(Exception):
    """Base class for exceptions in spkrepo"""


class SPKParseError(SpkrepoError):
    """Exception raised when SPK parsing fails"""


class SPKSignError(SpkrepoError):
    """Exception raised when SPK signing fails"""
