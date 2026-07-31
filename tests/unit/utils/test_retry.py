import pytest

from app.utils.retry import retry


class CustomError(Exception):
    pass


@pytest.mark.asyncio
async def test_retry_retries_on_exception():
    counter = {"calls": 0}

    @retry(retries=2, delay_seconds=0.01, max_delay_seconds=0.02, exceptions=CustomError)
    async def failing_operation():
        counter["calls"] += 1
        raise CustomError("fail")

    with pytest.raises(CustomError):
        await failing_operation()

    assert counter["calls"] == 3
