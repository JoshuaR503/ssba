"""External-computer client for the trained AI service. No RAG or motion commands."""

import os

import requests


class AiClient:
    def __init__(self, url: str, timeout: float = 10):
        self.url = url.rstrip("/")
        self.timeout = timeout
        token = os.environ.get("AI_API_TOKEN")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def analyze(self, payload: dict) -> dict:
        response = requests.post(f"{self.url}/ai/analyze", json=payload,
                                 headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
