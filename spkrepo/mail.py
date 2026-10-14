# -*- coding: utf-8 -*-
"""Transactional mail with bot-template suppression."""

import logging

from flask_security import MailUtil

logger = logging.getLogger(__name__)

# Security email templates that are only ever triggered by duplicate/replayed
# registration attempts — i.e. bots probing the register endpoint with
# already-taken usernames or victim email addresses — never by a legitimate
# first-time registration. Suppressing them (while keeping the generic
# response) stops bots from turning our mailer into a relay and burning the
# Postmark quota. All other templates (new-user welcome/confirmation, reset
# instructions, etc.) still send normally.
SUPPRESSED_BOT_TEMPLATES = frozenset(
    {
        "welcome_existing",
        "welcome_existing_username",
    }
)


def _template_basename(template: str) -> str:
    """Return a template name without its directory path."""
    return template.rsplit("/", 1)[-1]


class SpkrepoMailUtil(MailUtil):
    """MailUtil that drops bot-triggered registration emails.

    Wired in via ``Security(mail_util_cls=SpkrepoMailUtil)`` (see ext.py).
    """

    def send_mail(self, template, subject, recipient, sender, body, html, **kwargs):
        """Drop suppressed bot templates, otherwise send normally.

        Matches on the template's base name so the suppression holds wherever
        Flask-Security keeps its email templates. Returns ``None`` without
        sending when the template is suppressed; otherwise delegates to
        :meth:`flask_security.MailUtil.send_mail`.
        """
        if _template_basename(template) in SUPPRESSED_BOT_TEMPLATES:
            logger.warning(
                "Suppressed bot registration email %r to %r", template, recipient
            )
            return
        return super().send_mail(
            template, subject, recipient, sender, body, html, **kwargs
        )
