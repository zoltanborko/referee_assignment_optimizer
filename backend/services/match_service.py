"""Compatibility wrappers around the SQLite-backed match pool service."""

from services.match_pool_service import create_match_pool


def save_matches(matches):
    return create_match_pool(matches)
