from app.models.timeline import Segment, Timeline, VisualEvent, VisualSource


def test_timeline_builds_with_minimal_fields():
    timeline = Timeline(
        project_id="proj_123",
        style_preset="minimal",
        duration=30.0,
        segments=[Segment(id="seg_0", start=0.0, end=2.0, text="Hello world")],
        visual_events=[
            VisualEvent(
                segment_id="seg_0",
                source=VisualSource.STOCK_FOOTAGE,
                start=0.0,
                end=2.0,
                prompt="city skyline",
            )
        ],
    )
    assert timeline.duration == 30.0
    assert timeline.segments[0].text == "Hello world"
    assert timeline.visual_events[0].source == "stock_footage"
