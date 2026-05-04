from datetime import datetime

from services import DailyRunService, PostRunService, SignalEvaluationService


def test_daily_run_service_delegates_to_run_impl() -> None:
  calls: list[object] = []

  def _run_impl(args):
    calls.append(args)
    return (0, {"ok": True}, {}, datetime(2026, 1, 1))

  service = DailyRunService(run_impl=_run_impl)
  payload = object()
  result = service.run_daily_check(payload)

  assert calls == [payload]
  assert result[0] == 0
  assert result[1] == {"ok": True}


def test_signal_evaluation_service_delegates_to_impl() -> None:
  calls: list[tuple[dict, str]] = []

  def _eval_impl(state: dict, dashboard_url: str) -> dict:
    calls.append((state, dashboard_url))
    return {"transitions": [], "emailed": False}

  service = SignalEvaluationService(evaluate_impl=_eval_impl)
  state = {"paper_trades": []}
  result = service.evaluate_paper_trade_alerts(state, "https://example.test")

  assert calls == [(state, "https://example.test")]
  assert result == {"transitions": [], "emailed": False}


def test_post_run_service_delegates_dispatch_and_push() -> None:
  dispatch_calls: list[tuple] = []
  push_calls: list[tuple[dict, datetime]] = []

  def _dispatch_impl(state, old_signals, now, is_test, persist):
    dispatch_calls.append((state, old_signals, now, is_test, persist))

  def _push_impl(state: dict, now: datetime):
    push_calls.append((state, now))

  service = PostRunService(
    dispatch_impl=_dispatch_impl,
    push_impl=_push_impl,
  )
  now = datetime(2026, 1, 2)
  state = {"account": 1.0}
  service.dispatch_email_and_maintain_warnings(
    state,
    {"AUDUSD=X": 1},
    now,
    is_test=False,
    persist=True,
  )
  service.push_state_to_git(state, now)

  assert dispatch_calls == [(state, {"AUDUSD=X": 1}, now, False, True)]
  assert push_calls == [(state, now)]
