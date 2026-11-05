"""The peer under tests: it never reaches the network."""


class NullInstances:
    def send_event(self, event: dict) -> None:
        pass

    def retire(self, kind: str, ref_id) -> None:
        pass
