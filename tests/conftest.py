"""Shared pytest compatibility for the repository's Python 3.13 test runtime.

A small set of legacy synchronous tests intentionally drives async coroutines
with ``asyncio.get_event_loop().run_until_complete(...)``. Python 3.13 no
longer guarantees that ``get_event_loop()`` creates a loop after another test
has closed/reset it. The production runtime does not use this helper pattern;
this fixture only restores a disposable default loop for those synchronous
unit tests and closes any loop it creates after the test.

Do not use this fixture to hide production asyncio failures. Production code
must continue to own its async lifecycle explicitly.
"""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _python313_sync_asyncio_compat():
    """Provide a disposable default event loop when Python 3.13 has none."""
    created_loop = None
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        created_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(created_loop)

    yield

    if created_loop is not None and not created_loop.is_closed():
        created_loop.close()

    # Clear only the loop this fixture created. If another fixture/plugin owns
    # the current loop, leave it untouched.
    if created_loop is not None:
        try:
            current = asyncio.get_event_loop()
        except RuntimeError:
            current = None
        if current is created_loop:
            asyncio.set_event_loop(None)
