"""External data clients — the only network code in the project.

Every client writes raw pulls under ``fixtures/`` so the demo never depends on an
upstream being reachable. Event providers (NWS, AirNow, HMS, OpenFEMA, replay) land in M2;
the VA Facilities client (M1) lives in ``va_facilities``.
"""
