"""Canonical store labels shared by imports, reports, and history displays."""


def store_name(value):
    if isinstance(value, str) and ' '.join(value.upper().split()) in ('EULESS', '109 MARTHA ST SUITE 227', 'MARTHA'):
        return 'EULESS'
    return value


def store_labels(value):
    """Render current store labels without rewriting immutable audit snapshots."""
    if isinstance(value, list):
        return [store_labels(item) for item in value]
    if isinstance(value, dict):
        return {key: store_name(item) if key in ('store', 'store_name') else store_labels(item)
                for key, item in value.items()}
    return value
