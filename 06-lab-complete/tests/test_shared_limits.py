"""Integration tests against real Redis; each test owns a unique key prefix.

Run from 06-lab-complete with REDIS_URL pointing to a disposable Redis:
    python -m unittest discover -s tests -v
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from redis.exceptions import ConnectionError

from app import cost_guard, rate_limiter
from app.redis_client import r


class SharedLimitsTests(unittest.TestCase):
    def setUp(self):
        r.ping()
        self.environment = "cp5-test-" + uuid4().hex
        self.config = SimpleNamespace(
            environment=self.environment,
            rate_limit_per_minute=5,
            daily_budget_usd=Decimal("0.001"),
        )
        for module in (cost_guard, rate_limiter):
            replacement = patch.object(module, "settings", self.config)
            replacement.start()
            self.addCleanup(replacement.stop)

    def tearDown(self):
        keys = list(r.scan_iter(match=f"agent:{self.environment}:*"))
        if keys:
            r.delete(*keys)

    @staticmethod
    def outcome(call):
        try:
            call()
            return 200
        except HTTPException as error:
            return error.status_code

    def test_parallel_requests_share_exact_rate_quota(self):
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(
                lambda _: self.outcome(lambda: rate_limiter.check_rate_limit("test-key")), range(40)
            ))
        self.assertEqual(results.count(200), 5)
        self.assertEqual(results.count(429), 35)
        # Another credential has its own quota.
        rate_limiter.check_rate_limit("another-key")

    def test_expired_window_entries_do_not_consume_quota(self):
        bucket = f"agent:{self.environment}:rate:{sha256(b'test-key').hexdigest()}"
        seconds, _ = r.time()
        r.zadd(bucket, {str(i): seconds - 61 for i in range(5)})
        rate_limiter.check_rate_limit("test-key")
        self.assertEqual(r.zcard(bucket), 1)
        self.assertGreater(r.ttl(bucket), 0)

    def test_parallel_budget_reservations_cannot_overspend(self):
        def reserve(_):
            try:
                return cost_guard.check_budget(1000, 1000)
            except HTTPException as error:
                self.assertEqual(error.status_code, 402)
                return None

        with ThreadPoolExecutor(max_workers=20) as pool:
            reservations = [item for item in pool.map(reserve, range(20)) if item is not None]
        self.assertEqual(len(reservations), 1)
        reservation = reservations[0]
        self.assertEqual(int(r.get(reservation.key)), 750_000)
        # Settle lower actual usage, then reuse and refund the available budget.
        self.assertEqual(cost_guard.record_cost(1000, 0, reservation), 0.00015)
        second = cost_guard.check_budget(1000, 1000)
        self.assertEqual(int(r.get(second.key)), 900_000)
        cost_guard.release_cost(second)
        self.assertEqual(int(r.get(second.key)), 150_000)

    def test_new_utc_day_uses_fresh_budget(self):
        before_midnight = datetime.now(timezone.utc).replace(hour=23, minute=59, second=0, microsecond=0)
        with patch.object(cost_guard, "datetime") as clock:
            clock.now.return_value = before_midnight
            yesterday = cost_guard.check_budget(1000, 1000)
            self.assertEqual(self.outcome(lambda: cost_guard.check_budget(1000, 1000)), 402)
            clock.now.return_value = before_midnight + timedelta(minutes=1)
            today = cost_guard.check_budget(1000, 1000)
        self.assertNotEqual(yesterday.key, today.key)
        # A completion after midnight settles yesterday's reservation only.
        cost_guard.record_cost(1000, 0, yesterday)
        self.assertEqual(int(r.get(yesterday.key)), 150_000)
        self.assertEqual(int(r.get(today.key)), 750_000)

    def test_redis_failure_rejects_rate_and_budget_checks(self):
        for module, action in (
            (rate_limiter, lambda: rate_limiter.check_rate_limit("test-key")),
            (cost_guard, lambda: cost_guard.check_budget(1000, 1000)),
        ):
            with patch.object(module, "r") as unavailable:
                unavailable.eval.side_effect = ConnectionError("test outage")
                self.assertEqual(self.outcome(action), 503)


if __name__ == "__main__":
    unittest.main()
