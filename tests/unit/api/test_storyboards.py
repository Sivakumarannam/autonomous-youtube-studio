from uuid import uuid4

from app.database.models.channel import Channel
from app.database.models.topic import Topic
from app.database.models.script import Script, ScriptType


async def create_script(test_session):
    channel = Channel(
        id=uuid4(),
        name="Test Channel",
        niche="Education",
        language="en",
    )

    topic = Topic(
        id=uuid4(),
        channel_id=channel.id,
        title="Test Topic",
        score=90,
    )

    script = Script(
        id=uuid4(),
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=ScriptType.SHORT,
        content="This is a test script.",
        word_count=5,
        estimated_duration=10,
    )

    test_session.add(channel)
    test_session.add(topic)
    test_session.add(script)

    await test_session.commit()
    await test_session.refresh(script)

    return script