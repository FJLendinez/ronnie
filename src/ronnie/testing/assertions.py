"""Assertion helpers mixed into Ronnie test cases."""

from __future__ import annotations

from typing import Any, NoReturn

__all__ = ["AssertionsMixin"]


class AssertionsMixin:
    """Django-flavoured response assertions usable with RonnieTestClient."""

    # Match typeshed's TestCase declarations for MRO compatibility.
    failureException: type[BaseException] = AssertionError

    def fail(self, msg: Any = None) -> NoReturn:
        raise self.failureException(msg or "fail() called")

    def assertRedirects(
        self,
        response: Any,
        expected_url: str,
        status_code: int | tuple[int, ...] = (302, 303),
        target_status_code: int = 200,
        fetch_redirect_response: bool = True,
        msg_prefix: str = "",
    ) -> Any:
        """Assert ``response`` redirects to ``expected_url`` (following it by default)."""
        if response.history:
            final = response
            redirect = response.history[0]
        else:
            redirect, final = response, None

        codes = status_code if isinstance(status_code, tuple) else (status_code,)
        if redirect.status_code not in codes:
            self.fail(f"{msg_prefix}Expected status {codes}, got {redirect.status_code}.")
        location = redirect.headers.get("location", "")
        if location.rstrip("/") != expected_url.rstrip("/") and location != expected_url:
            self.fail(f"{msg_prefix}Expected redirect to {expected_url!r}, got {location!r}.")
        if not fetch_redirect_response:
            return response

        client = getattr(self, "client", None)
        if client is None or final is None:
            return response
        if final.status_code != target_status_code:
            self.fail(
                f"{msg_prefix}Redirect target returned {final.status_code}, expected {target_status_code}."
            )
        return final

    def assertContains(
        self,
        response: Any,
        text: str,
        count: int | None = None,
        status_code: int = 200,
        msg_prefix: str = "",
    ) -> None:
        if response.status_code != status_code:
            self.fail(f"{msg_prefix}Expected status {status_code}, got {response.status_code}.")
        real_count = response.text.count(text)
        if count is not None and real_count != count:
            self.fail(f"{msg_prefix}Found {real_count} occurrences of {text!r}, expected {count}.")
        if count is None and real_count < 1:
            self.fail(f"{msg_prefix}Couldn't find {text!r} in response (len {len(response.text)}).")

    def assertNotContains(
        self,
        response: Any,
        text: str,
        status_code: int = 200,
        msg_prefix: str = "",
    ) -> None:
        if response.status_code != status_code:
            self.fail(f"{msg_prefix}Expected status {status_code}, got {response.status_code}.")
        if text in response.text:
            self.fail(f"{msg_prefix}Unexpectedly found {text!r} in response.")
