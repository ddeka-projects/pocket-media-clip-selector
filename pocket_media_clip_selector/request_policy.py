"""Trusted-LAN host, peer, and same-origin request checks."""

import ipaddress
import socket
from urllib.parse import urlsplit

from .errors import AppError


def validate_request(request, settings):
    try:
        address = ipaddress.ip_address(request.client.host)
        if not (address.is_loopback or address.is_private or address.is_link_local):
            raise ValueError("public peer")
        parsed = urlsplit("http://" + request.headers.get("host", ""))
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or port == 0
        ):
            raise ValueError("invalid host")
        if not host:
            raise ValueError("missing host")
        names = {"localhost", socket.gethostname().casefold(), socket.getfqdn().casefold()}
        if settings.host not in ("0.0.0.0", "::"):
            names.add(settings.host.casefold())
        if host.casefold() not in names:
            host_ip = ipaddress.ip_address(host)
            if (
                not (host_ip.is_private or host_ip.is_loopback or host_ip.is_link_local)
                or host_ip.is_unspecified
            ):
                raise ValueError("public host")
    except (ValueError, AttributeError):
        raise AppError(
            "Open the app from this PC's private-network URL.", 403, "forbidden_request"
        ) from None
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise AppError("Cross-site requests are not allowed.", 403, "foreign_origin")
