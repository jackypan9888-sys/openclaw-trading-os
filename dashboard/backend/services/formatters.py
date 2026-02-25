"""Value format helpers for textual AI replies."""

def format_market_cap(cap):
    if not cap:
        return "N/A"
    if cap >= 1e12:
        return f"${cap/1e12:.2f}T"
    if cap >= 1e9:
        return f"${cap/1e9:.2f}B"
    if cap >= 1e6:
        return f"${cap/1e6:.2f}M"
    return f"${cap:,.0f}"


def format_volume(vol):
    if not vol:
        return "N/A"
    if vol >= 1e9:
        return f"{vol/1e9:.2f}B"
    if vol >= 1e6:
        return f"{vol/1e6:.2f}M"
    if vol >= 1e3:
        return f"{vol/1e3:.2f}K"
    return f"{vol:,.0f}"
