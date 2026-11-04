"""The peer under tests: unreachable, so a test that needs it says so."""

from common.peers import PeerUnavailable


class UnreachableCatalog:
    def fetch(self, kind: str, ref_id):
        raise PeerUnavailable(f"catalog is not running in tests ({kind} {ref_id})")

    def iter_snapshots(self, kind: str):
        raise PeerUnavailable(f"catalog is not running in tests ({kind})")
