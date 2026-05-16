'''Tests for news_filter.py — Phase 38 NEWS-02 keyword classifier.

Fixture: tests/fixtures/news/news_classifier_30.json is a 30-headline sanity-check,
not a statistically significant benchmark (±15-20% CI at 95% on 30 samples). It
exists to catch grossly miscalibrated keyword sets. Real production tuning would
require a labelled corpus 10x+ larger.
'''
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from news_fetcher import NewsResult
from news_filter import CriticalEventResult, classify_headline, has_critical_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_classifier_fixture():
  '''Load the 30-headline sanity-check fixture.'''
  fixture_path = Path(__file__).parent / 'fixtures' / 'news' / 'news_classifier_30.json'
  with open(fixture_path) as fh:
    return json.load(fh)


# ---------------------------------------------------------------------------
# classify_headline — unknown market
# ---------------------------------------------------------------------------

def test_classify_headline_unknown_market_returns_false():
  assert classify_headline('RBA cuts rates', 'UNKNOWN_MKT') is False


def test_classify_headline_unknown_market_logs_warning(caplog):
  with caplog.at_level(logging.WARNING):
    classify_headline('x', 'UNKNOWN_MKT')
  assert any(
    'UNKNOWN_MKT' in r.message and r.levelno == logging.WARNING
    for r in caplog.records
  ), 'Expected WARNING log containing UNKNOWN_MKT'


# ---------------------------------------------------------------------------
# classify_headline — positive keyword matches
# ---------------------------------------------------------------------------

def test_classify_headline_spi200_rate_hike_match():
  assert classify_headline('RBA hikes interest rate to 4.35%', 'SPI200') is True


def test_classify_headline_audusd_fomc_match():
  assert classify_headline('Fed FOMC signals rate cut path', 'AUDUSD') is True


# ---------------------------------------------------------------------------
# classify_headline — dampener suppression
# ---------------------------------------------------------------------------

def test_dampener_suppresses_first_rate():
  '''Dampener: "first-rate" contains "rate" but is not a rate decision signal.'''
  assert classify_headline('first-rate service from ASX broker', 'SPI200') is False


def test_dampener_does_not_suppress_real_rate_news():
  '''Dampener removes "first-rate" but real keyword "rate cut" survives.'''
  assert classify_headline('first-rate service after RBA rate cut', 'SPI200') is True


# ---------------------------------------------------------------------------
# classify_headline — edge cases
# ---------------------------------------------------------------------------

def test_classify_headline_empty_string_returns_false():
  assert classify_headline('', 'SPI200') is False


def test_classify_headline_case_insensitive():
  assert classify_headline('RBA CUTS RATES', 'SPI200') is True
  assert classify_headline('rba cuts rates', 'SPI200') is True


def test_word_boundary_no_substring_match():
  '''Word-boundary anchors prevent substring false positives.'''
  assert classify_headline('integration testing news', 'SPI200') is False


# ---------------------------------------------------------------------------
# has_critical_event — D-02 CriticalEventResult contract
# ---------------------------------------------------------------------------

def _make_result(items=None, error=None):
  '''Helper: build a NewsResult for test use.'''
  return NewsResult(
    items=items or [],
    error=error,
    fetched_at=datetime.now(UTC),
  )


def test_has_critical_event_any_match_fires():
  headlines = [{'title': 'sport results'}, {'title': 'RBA rate cut'}]
  result = _make_result(items=headlines)
  event = has_critical_event(result, 'SPI200')
  assert isinstance(event, CriticalEventResult)
  assert event.triggered is True
  assert event.gate_status == 'blocked'
  assert event.fetch_error is None


def test_has_critical_event_no_match_returns_false():
  headlines = [{'title': 'sport results'}, {'title': 'penny stock tip'}]
  result = _make_result(items=headlines)
  event = has_critical_event(result, 'SPI200')
  assert event.triggered is False
  assert event.gate_status == 'clear'
  assert event.fetch_error is None


def test_has_critical_event_handles_missing_title_key():
  '''Missing title key must not raise KeyError.'''
  result = _make_result(items=[{'no_title': 'x'}])
  event = has_critical_event(result, 'SPI200')
  assert event.triggered is False
  assert event.gate_status == 'clear'


def test_has_critical_event_accepts_newsitem_typed_dicts():
  '''Accepts list of dicts matching NewsItem shape (title, url, publisher, pub_date, title_hash).'''
  headlines = [
    {
      'title': 'RBA cuts interest rate to support growth',
      'url': 'https://example.com/rba',
      'publisher': 'AFR',
      'pub_date': '2026-05-16',
      'title_hash': 'abc123',
    }
  ]
  result = _make_result(items=headlines)
  event = has_critical_event(result, 'SPI200')
  assert event.triggered is True
  assert event.gate_status == 'blocked'


def test_has_critical_event_returns_unknown_on_fetch_error():
  '''D-02: fetch failure → gate_status="unknown" (fail-closed).'''
  result = _make_result(items=[], error='timeout')
  event = has_critical_event(result, 'SPI200')
  assert isinstance(event, CriticalEventResult)
  assert event.triggered is False
  assert event.gate_status == 'unknown'
  assert event.fetch_error == 'timeout'


def test_has_critical_event_unknown_on_network_error():
  '''D-02: network_unreachable also triggers unknown gate_status.'''
  result = _make_result(items=[], error='network_unreachable')
  event = has_critical_event(result, 'SPI200')
  assert event.gate_status == 'unknown'
  assert event.fetch_error == 'network_unreachable'


def test_has_critical_event_clear_on_successful_no_news():
  '''D-02: successful empty fetch → gate_status="clear" (no block).'''
  result = _make_result(items=[], error=None)
  event = has_critical_event(result, 'SPI200')
  assert event.gate_status == 'clear'
  assert event.triggered is False
  assert event.fetch_error is None


# ---------------------------------------------------------------------------
# Precision / recall gate — 30-headline sanity-check fixture (D-07)
# ---------------------------------------------------------------------------

def test_classifier_precision_recall():
  '''30-headline sanity-check: precision >= 0.7 AND recall >= 0.9 (D-07).

  NOTE: fixture is a heuristic gate, not statistically significant. CI ±15-20%
  at 95% on 30 samples. Exists to catch grossly miscalibrated keyword sets only.
  '''
  items = _load_classifier_fixture()
  tp = fp = fn = 0
  for item in items:
    pred = classify_headline(item['title'], item['market'])
    label = item['label']
    if pred and label:
      tp += 1
    elif pred and not label:
      fp += 1
    elif not pred and label:
      fn += 1

  precision = tp / (tp + fp) if (tp + fp) else 1.0
  recall = tp / (tp + fn) if (tp + fn) else 0.0

  assert precision >= 0.7, (
    f'Precision {precision:.3f} < 0.7 (tp={tp}, fp={fp}, fn={fn}). '
    'Keyword set has too many false positives — tune NEWS_KEYWORDS or dampener.'
  )
  assert recall >= 0.9, (
    f'Recall {recall:.3f} < 0.9 (tp={tp}, fp={fp}, fn={fn}). '
    'Keyword set misses too many critical events — add missing keywords to system_params.'
  )
