"""Jev (TypeSafe) HTTP client with bounded retries, plus the shared spend ledger.

Every HTTP attempt (success or failure) is reported to a callback so it lands in calls.jsonl.
Raw HTTP instead of the SDK: the SDK retries internally, which would hide attempts we must log.
"""

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .common import write_json

API_URL = "https://api.typesafe.ai/v1/systemone"
# USD per input token ($0.042 / 1M). Output tokens are free. Source: https://docs.typesafe.ai/models (checked 2026-10-05)
DEFAULT_INPUT_RATE = 0.042 / 1_000_000
DEFAULT_OUTPUT_RATE = 0.0


class FatalAPIError(Exception):
    """Auth/credit/validation problems: retrying will not help, stop the run."""


class RateLimiter:
    """Token buckets shared by every worker, so concurrency cannot exceed the published Jev limits
    (100K tokens/s, 80 requests/s; https://docs.typesafe.ai/models, checked 2026-10-05). Defaults sit
    at 60% of those so retries and burstiness still have headroom."""

    def __init__(self, tokens_per_s=60_000, requests_per_s=48):
        self.lock = threading.Lock()
        self.rates = {"tokens": float(tokens_per_s), "requests": float(requests_per_s)}
        self.allow = {"tokens": float(tokens_per_s), "requests": float(requests_per_s)}
        self.last = time.monotonic()
        self.waited_s = 0.0

    def acquire(self, est_tokens):
        """Block until this request fits both buckets."""
        want = {"tokens": min(float(est_tokens), self.rates["tokens"]), "requests": 1.0}
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed, self.last = now - self.last, now
                for k, rate in self.rates.items():
                    self.allow[k] = min(rate, self.allow[k] + elapsed * rate)
                if all(self.allow[k] >= want[k] for k in want):
                    for k in want:
                        self.allow[k] -= want[k]
                    return
                delay = max((want[k] - self.allow[k]) / self.rates[k] for k in want)
                self.waited_s += delay
            time.sleep(min(delay, 0.25))


class BudgetExceeded(Exception):
    pass


class SpendLedger:
    """One ledger shared by all workers. Before each call we reserve a worst-case cost; the call is
    refused if spent + reserved + this reservation would exceed either cap. After the call, the
    reservation is replaced by the actual cost. Unknown-outcome calls (timeouts) keep their
    reservation as spent, so the estimate stays conservative.

    Two caps: a per-run cap (--max-spend) and a project-wide cap persisted in state/ledger.json
    that survives across runs (protects the prepaid credit)."""

    def __init__(self, run_cap_usd, global_path, global_cap_usd=None):
        self.lock = threading.Lock()
        self.run_cap = float(run_cap_usd)
        self.global_path = Path(global_path)
        state = json.loads(self.global_path.read_text()) if self.global_path.exists() else {}
        self.global_spent_before = float(state.get("spent_usd", 0.0))
        self.global_cap = float(global_cap_usd if global_cap_usd is not None else state.get("cap_usd", 4.00))
        self.run_spent = 0.0
        self.reserved = 0.0

    def reserve(self, amount):
        with self.lock:
            run_total = self.run_spent + self.reserved + amount
            global_total = self.global_spent_before + run_total
            if run_total > self.run_cap:
                raise BudgetExceeded(f"run cap ${self.run_cap:.4f} would be exceeded "
                                     f"(spent ${self.run_spent:.6f}, reserved ${self.reserved:.6f}, next ${amount:.6f})")
            if global_total > self.global_cap:
                raise BudgetExceeded(f"project cap ${self.global_cap:.2f} would be exceeded "
                                     f"(all-time spent ${self.global_spent_before + self.run_spent:.6f})")
            self.reserved += amount

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.run_spent += actual
            self._persist()

    def _persist(self):
        write_json(self.global_path, {"cap_usd": self.global_cap,
                                      "spent_usd": round(self.global_spent_before + self.run_spent, 9),
                                      "note": "Local estimate from logged usage x rates; provider billing is authoritative."})


class JevClient:
    def __init__(self, ledger, on_attempt, timeout=30, max_attempts=3, input_rate=DEFAULT_INPUT_RATE,
                 limiter=None):
        self.key = os.environ.get("TYPESAFE_API_KEY", "")
        if not self.key:
            raise FatalAPIError("TYPESAFE_API_KEY is not set (copy .env.example to .env and fill it in)")
        self.ledger = ledger
        self.on_attempt = on_attempt
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.input_rate = input_rate
        self.limiter = limiter or RateLimiter()

    def ask(self, state, questions, model, est_tokens, context):
        """One request = one review (`state`) with several questions. Returns (response_json, attempts).
        `context` is merged into every logged attempt (role, review_ids, phase, label_config...)."""
        body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
        reservation = est_tokens * self.input_rate
        last_err = None
        for attempt in range(1, self.max_attempts + 1):
            self.ledger.reserve(reservation)   # refuse before spending, not after
            self.limiter.acquire(est_tokens)   # then wait for rate-limit headroom
            t0 = time.monotonic()
            started = time.time()
            status, payload, err = None, None, None
            try:
                req = urllib.request.Request(API_URL, data=body, method="POST", headers={
                    "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    request_id = resp.headers.get("x-request-id") or resp.headers.get("request-id")
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                status, request_id = e.code, e.headers.get("x-request-id") if e.headers else None
                err = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                request_id = None
                err = f"transport: {type(e).__name__}: {e}"
            duration = time.monotonic() - t0

            usage = (payload or {}).get("usage") or {}
            in_tok, out_tok = usage.get("input_tokens"), usage.get("output_tokens")
            if payload is not None and isinstance(in_tok, int):
                actual, usage_known = in_tok * self.input_rate, True
            elif status is not None and 400 <= status < 500 and status != 429:
                actual, usage_known = 0.0, True  # rejected before processing; not billed
            else:
                actual, usage_known = reservation, False  # unknown outcome: count the reservation
            self.ledger.settle(reservation, actual)

            outcome = "succeeded" if payload is not None else "failed"
            self.on_attempt({
                **context,
                # Jev does not return a provider request id, so synthesize one that is unique across
                # runs: the same text chunk reprocessed in another run must not reuse an id.
                "request_id": request_id or f"local-{context.get('run_id', '')}-{context.get('call_id', '')}-a{attempt}",
                "attempt": attempt, "outcome": outcome, "http_status": status, "error": err,
                "model": (payload or {}).get("model", context.get("model")),
                "input_tokens": in_tok, "output_tokens": out_tok, "usage_known": usage_known,
                "cost_usd_estimate": round(actual, 10),
                "started_at": started, "duration_s": round(duration, 4),
            })
            if payload is not None:
                return payload, attempt
            last_err = err
            if status in (401, 402, 403, 422):
                raise FatalAPIError(err)
            if attempt < self.max_attempts:  # 429/529/5xx/timeouts: bounded backoff with jitter
                time.sleep(min(8, 2 ** (attempt - 1)) + random.uniform(0, 0.5))
        raise TransientFailure(last_err)


class TransientFailure(Exception):
    pass
