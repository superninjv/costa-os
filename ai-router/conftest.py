"""Pytest configuration for ai-router tests."""


def pytest_configure(config):
    config.addinivalue_line("markers", "live: tests requiring a running Ollama instance")
