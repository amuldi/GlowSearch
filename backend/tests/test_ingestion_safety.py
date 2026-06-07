import pytest

from app.ingestion.safety import (
    AsyncRateLimiter,
    RetryConfig,
    backoff_delay_seconds,
    is_bot_detection_response,
)


@pytest.mark.asyncio
async def test_async_rate_limiter_sleeps_between_requests() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    limiter = AsyncRateLimiter(requests_per_second=2, sleep=fake_sleep)

    await limiter.wait()
    await limiter.wait()

    assert len(sleeps) == 1
    assert sleeps[0] <= 0.5
    assert sleeps[0] > 0


def test_backoff_delay_uses_exponential_cap_without_jitter() -> None:
    config = RetryConfig(base_delay_seconds=0.5, max_delay_seconds=2.0, jitter_ratio=0)

    assert backoff_delay_seconds(0, config) == 0.5
    assert backoff_delay_seconds(1, config) == 1.0
    assert backoff_delay_seconds(3, config) == 2.0


def test_bot_detection_finds_status_and_cloudflare_markers() -> None:
    assert is_bot_detection_response(status_code=429)
    assert is_bot_detection_response(
        status_code=200,
        text="<title>잠시만 기다려 주세요 - 올리브영</title><script>cf_chl</script>",
    )
    assert not is_bot_detection_response(status_code=200, text='{"success": true}')


def test_bot_detection_does_not_treat_cloudflare_cdn_header_as_challenge() -> None:
    assert not is_bot_detection_response(
        status_code=200,
        text='{"success": true}',
        headers={"server": "cloudflare"},
    )
    assert is_bot_detection_response(
        status_code=200,
        text="",
        headers={"cf-mitigated": "challenge"},
    )
