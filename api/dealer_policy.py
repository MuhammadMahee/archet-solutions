"""Active portal dealers. Archived data remains intact for record keeping."""

RETIRED_DEALERS = frozenset({'AMQ'})
RETIRED_SOURCES = frozenset({'arm1'})


def active_dealer(dealer):
    return dealer not in RETIRED_DEALERS
