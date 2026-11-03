from __future__ import annotations

from typing import Any, Mapping

import httpx


class EvaluationClient:
    """HTTP client that logs in once per role and asks questions."""

    def __init__(
        self,
        base_url: str,
        role_passwords: Mapping[str, str],
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.role_passwords = dict(role_passwords)
        self._client = http_client
        self._tokens: dict[str, str] = {}

    async def _http(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(timeout=30.0)

    async def login(self, role: str) -> str:
        if role in self._tokens:
            return self._tokens[role]
        if role not in self.role_passwords:
            raise ValueError(f"No evaluation password configured for role '{role}'.")
        client = await self._http()
        response = await client.post(
            f"{self.base_url}/auth/login",
            json={"username": f"{role}.demo", "password": self.role_passwords[role]},
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self._tokens[role] = token
        return token

    async def ask(
        self,
        role: str,
        question: str,
        conversation_id: str | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        token = await self.login(role)
        client = await self._http()
        payload: dict[str, Any] = {"question": question}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        for attempt in range(2):
            headers = {"Authorization": "Bearer " + token}
            if case_id:
                headers["X-Evaluation-Case-ID"] = case_id
            response = await client.post(
                f"{self.base_url}/ask",
                headers=headers,
                json=payload,
            )
            if response.status_code != 401:
                response.raise_for_status()
                return response.json()
            token = await self._login_fresh(role)
            if attempt:
                response.raise_for_status()
        raise RuntimeError("Authentication failed after retry.")

    async def _login_fresh(self, role: str) -> str:
        self._tokens.pop(role, None)
        return await self.login(role)

    async def close(self) -> None:
        if self._client is None:
            client = await self._http()
            await client.aclose()
