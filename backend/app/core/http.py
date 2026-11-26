"""Keep CORS outside Starlette's error handler, including unexpected 500s. Centralize client IP extraction."""
from __future__ import annotations

import ipaddress

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.config import get_settings


class CorsFastAPI(FastAPI):
    def build_middleware_stack(self):
        return CORSMiddleware(
            super().build_middleware_stack(),
            allow_origins=get_settings().app_cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )


def _parse_ip(candidate: str | None) -> str | None:
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate:
        return None
    try:
        ip = ipaddress.ip_address(candidate)
        return str(ip)
    except ValueError:
        return None


def get_client_ip(request: Request | None) -> str | None:
    """Extract and validate the originating client IP address.

    - Returns direct peer IP (request.client.host) if valid.
    - Only checks forwarding headers (X-Forwarded-For / X-Real-IP) if the direct peer
      is in the configured trusted_proxies list.
    - Validates IPv4 and IPv6 format.
    - Never fabricates an IP; returns None if undetermined.
    """
    if request is None:
        return None

    client = getattr(request, "client", None)
    if client is None:
        return None

    raw_peer = getattr(client, "host", None)
    peer_ip = _parse_ip(raw_peer)
    if peer_ip is None:
        return None

    settings = get_settings()
    trusted = getattr(settings, "trusted_proxies", [])

    is_trusted = False
    if trusted:
        try:
            peer_obj = ipaddress.ip_address(peer_ip)
            for proxy in trusted:
                try:
                    if "/" in proxy:
                        if peer_obj in ipaddress.ip_network(proxy, strict=False):
                            is_trusted = True
                            break
                    elif peer_obj == ipaddress.ip_address(proxy):
                        is_trusted = True
                        break
                except ValueError:
                    continue
        except ValueError:
            pass

    if is_trusted:
        # Check X-Forwarded-For (client is the leftmost IP in the chain)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            for part in forwarded_for.split(","):
                forwarded_ip = _parse_ip(part)
                if forwarded_ip:
                    return forwarded_ip

        # Check X-Real-IP
        real_ip = _parse_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return real_ip

    return peer_ip
