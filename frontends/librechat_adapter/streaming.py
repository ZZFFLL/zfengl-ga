from dataclasses import dataclass


@dataclass
class DeltaTracker:
    last_snapshot: str = ""
    regressed: bool = False

    def consume_snapshot(self, current_full_text) -> str:
        current_full_text = "" if current_full_text is None else str(current_full_text)

        if current_full_text.startswith(self.last_snapshot):
            delta = current_full_text[len(self.last_snapshot) :]
            self.last_snapshot = current_full_text
            return delta

        self.regressed = True
        self.last_snapshot = current_full_text
        return ""
