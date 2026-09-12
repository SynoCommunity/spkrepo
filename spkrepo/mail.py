# -*- coding: utf-8 -*-
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


class SpkrepoMailUtil(MailUtil):
    """MailUtil that drops bot-triggered registration emails.

    Wired in via ``Security(mail_util_cls=SpkrepoMailUtil)`` (see ext.py).
    """

    def send_mail(self, template, subject, recipient, sender, body, html, **kwargs):
        if template in SUPPRESSED_BOT_TEMPLATES:
            logger.warning(
                "Suppressed bot registration email %r to %r", template, recipient
            )
            return
        return super().send_mail(
            template, subject, recipient, sender, body, html, **kwargs
        )
