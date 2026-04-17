"""Tests for models.cope_input — CopeEndSpec dataclass."""

from models.cope_input import CopeEndSpec
from models.cope_data import ReceivingTube


class TestCopeEndSpecCreation:
    """Basic construction and field access."""

    def test_creation_defaults(self) -> None:
        spec = CopeEndSpec(end="start", receiving_tubes=[])
        assert spec.end == "start"
        assert spec.receiving_tubes == []
        assert spec.label == ""

    def test_creation_with_label(self) -> None:
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.5, name="Cross tube")
        spec = CopeEndSpec(end="end", receiving_tubes=[rt], label="Front Node")
        assert spec.label == "Front Node"
        assert len(spec.receiving_tubes) == 1
        assert spec.receiving_tubes[0].od == 1.5

    def test_end_literal_start(self) -> None:
        spec = CopeEndSpec(end="start", receiving_tubes=[])
        assert spec.end == "start"

    def test_end_literal_end(self) -> None:
        spec = CopeEndSpec(end="end", receiving_tubes=[])
        assert spec.end == "end"

    def test_multiple_receiving_tubes(self) -> None:
        tubes = [
            ReceivingTube(vector=(1.0, 0.0, 0.0), od=1.5),
            ReceivingTube(vector=(0.0, 0.0, 1.0), od=2.0, name="Vertical"),
        ]
        spec = CopeEndSpec(end="end", receiving_tubes=tubes, label="Node A")
        assert len(spec.receiving_tubes) == 2
        assert spec.receiving_tubes[1].name == "Vertical"
