"""Nitaq (نِطاق): discover, scan and (opt-in) protect AI agent setups against prompt injection.

Why the name: nitaq (نِطاق) is Arabic for *scope*.  Every task gets a scope (the tools,
destinations and files it needs) and Nitaq checks each tool call against it.  It decides from
the call itself (destinations, files), never from the language of the text, so Egyptian
Arabic, Arabizi or Base64 make no difference to it.  Any action outside the scope is refused.

The research benchmark lives in the `nitaq_bench` package (its scanners are frozen); this
package adds discovery, installation and opt-in protection on top of it.

Nitaq reduces the damage an injected instruction can cause; it does not stop a
model from following it.
"""

__version__ = "1.1.0"
