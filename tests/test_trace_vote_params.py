'''Regression suite for commits 587b6f0 + bb780af — trace vote_params locality.

Phase 29 plan 29-03 (DEBT-02). Locks:
- 587b6f0: render engine-resolved vote params instead of re-derived defaults
- bb780af: backfill vote_params at render time for stale state rows

Project LEARNING 2026-05-10: "When a renderer's job is to audit a decision the
engine already made, it MUST read the inputs+outputs the engine recorded, not
re-derive them from defaults."  This suite locks that discipline out permanently.

Tests:
- test_trace_renders_engine_resolved_vote_params: gate badge uses persisted adx_gate
- test_trace_falls_back_at_render_time_for_stale_signal_row: no crash + fallback works
- test_trace_prelim_vote_uses_resolved_momentum_threshold: mom below threshold is not a vote
- test_trace_gate_text_reflects_custom_adx_gate: ">= 20" not ">= 25" in HTML
- test_trace_renders_without_vote_params_key: stale row (no key) falls back gracefully
'''

from dashboard_renderer.components.trace import _render_trace_vote, _render_trace_panels


class TestTraceVoteParams:
    '''Regression suite for 587b6f0 + bb780af — trace vote_params locality.

    Project LEARNING 2026-05-10: trace panel must read engine-resolved persisted
    vote_params, never re-derive from defaults. This suite ensures that:
    1. A persisted adx_gate=20.0 shows "FAIL" when ADX=18.66 (not the old "PASS"
       that the hardcoded 25.0 threshold would have produced).
    2. A stale state row without vote_params does not crash and falls back to the
       same values resolve_vote_params({}) would return.
    3. The prelim Vote line counts Mom values against the persisted threshold, not
       a hardcoded 0.0, so Mom1=0.0074 does NOT vote positive when threshold=0.02.
    '''

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _scalars_with(
        self,
        adx: float = 18.66,
        mom1: float = 0.0074,
        mom3: float = 0.025,
        mom12: float = 0.031,
    ) -> dict:
        return {
            'adx': adx,
            'atr': 50.0,
            'mom1': mom1,
            'mom3': mom3,
            'mom12': mom12,
            'rvol': 1.0,
            'pdi': 20.0,
            'ndi': 15.0,
        }

    def _vote_params_custom(
        self,
        adx_gate: float = 20.0,
        momentum_threshold: float = 0.02,
        momentum_votes_required: int = 2,
        direction_mode: str = 'both',
    ) -> dict:
        return {
            'adx_gate': adx_gate,
            'momentum_threshold': momentum_threshold,
            'momentum_votes_required': momentum_votes_required,
            'direction_mode': direction_mode,
        }

    # -----------------------------------------------------------------------
    # Tests
    # -----------------------------------------------------------------------

    def test_trace_renders_engine_resolved_vote_params(self) -> None:
        '''Engine persisted adx_gate=20.0; ADX=18.66. Trace must show "FAIL".

        Bug pre-587b6f0: trace hardcoded 25.0, so ADX 18.66 vs 25.0 also FAILs
        but for the wrong reason. The assertion here is more precise: the gate
        text must say ">= 20" (the persisted value), not ">= 25" (the default).

        This test catches any future reversion where the renderer re-derives the
        gate from defaults instead of reading vote_params.
        '''
        scalars = self._scalars_with(adx=18.66)
        vote_params = self._vote_params_custom(adx_gate=20.0)
        html = _render_trace_vote(scalars, signal=0, vote_params=vote_params)

        # Gate badge must show FAIL (18.66 < 20.0)
        assert '<span class="trace-badge fail">FAIL</span>' in html, (
            '587b6f0: ADX 18.66 with gate 20.0 must show FAIL badge'
        )
        # Gate text must reference the persisted threshold, not the default 25.0
        # _render_trace_vote HTML-escapes the gate text, so ">=" → "&gt;="
        assert '&gt;= 20' in html, (
            '587b6f0: gate text must show "&gt;= 20" (persisted adx_gate); '
            'finding "&gt;= 25" means the renderer is using the default instead'
        )
        assert '&gt;= 25' not in html, (
            '587b6f0: gate text must NOT show "&gt;= 25" (hardcoded default) when '
            'persisted adx_gate=20.0 was passed in vote_params'
        )

    def test_trace_falls_back_at_render_time_for_stale_signal_row(self) -> None:
        '''State row without vote_params key must render without crashing.

        bb780af adds a render-time fallback so pre-587b6f0 state.json rows (which
        have no vote_params field) still render. The fallback uses the same values
        as signal_engine.resolve_vote_params({}).

        This test calls _render_trace_vote with vote_params=None (the pre-backfill
        shape) and asserts no exception + the fallback default (adx_gate=25.0) is used.
        '''
        from signal_engine import resolve_vote_params
        scalars = self._scalars_with(adx=30.0, mom1=0.03, mom3=0.03, mom12=0.03)

        # Pass vote_params=None to simulate stale state row (bb780af fallback path)
        html = _render_trace_vote(scalars, signal=1, vote_params=None)

        # Must not crash and must render gate text
        assert 'ADX gate' in html, (
            'bb780af: _render_trace_vote with vote_params=None must still render '
            'the ADX gate row (fallback to defaults)'
        )
        # Fallback default is adx_gate=25.0 per resolve_vote_params({})
        fallback = resolve_vote_params({})
        expected_gate = fallback['adx_gate']
        # gate text is HTML-escaped: ">= N" → "&gt;= N"
        assert f'&gt;= {expected_gate:g}' in html, (
            f'bb780af: stale-state fallback must use adx_gate={expected_gate} '
            f'(from resolve_vote_params({{}})); gate text not found in HTML'
        )

    def test_trace_prelim_vote_uses_resolved_momentum_threshold(self) -> None:
        '''Mom1=0.0074 with threshold=0.02: Mom1 must NOT vote positive.

        Pre-587b6f0 bug: the prelim Vote line counted `v > 0` (any positive
        value) instead of `v > momentum_threshold`. A Mom1 of 0.0074 was treated
        as a positive vote even though the engine requires > 0.02.

        This test constructs exactly the scenario that exposed the bug in production
        (SPI 200 card showed "Vote: LONG / FINAL: FLAT" while the engine used
        adx_gate=20 and threshold=0.02).

        With persisted vote_params carrying momentum_threshold=0.02, Mom1=0.0074
        does not exceed the threshold and does NOT count as a positive vote.
        Only mom3 and mom12 vote if they exceed 0.02.
        '''
        # mom1=0.0074 is below threshold=0.02 — must NOT vote
        # mom3=0.025, mom12=0.031 both above threshold — both vote positive
        # 2 positive votes with votes_required=2 → prelim=LONG
        scalars = self._scalars_with(
            adx=22.0,  # above adx_gate=20.0 → gate PASS
            mom1=0.0074,  # below threshold=0.02 — must NOT count
            mom3=0.025,   # above threshold — counts
            mom12=0.031,  # above threshold — counts
        )
        vote_params = self._vote_params_custom(
            adx_gate=20.0,
            momentum_threshold=0.02,
            momentum_votes_required=2,
        )
        html = _render_trace_vote(scalars, signal=1, vote_params=vote_params)

        # With threshold=0.02 only mom3 and mom12 vote → prelim=LONG (2 votes)
        # (engine uses the same logic → signal=LONG matches)
        assert 'Vote: LONG' in html, (
            '587b6f0: with mom3=0.025 and mom12=0.031 above threshold=0.02, '
            'prelim vote must be LONG (2 positive votes); '
            'mom1=0.0074 must NOT count'
        )

    def test_trace_gate_text_reflects_custom_adx_gate(self) -> None:
        '''The gate text ">= N" reflects the persisted adx_gate, not the default.

        Simplest regression guard: if adx_gate=15.0 is persisted, the HTML must
        contain ">= 15", not ">= 25".
        '''
        scalars = self._scalars_with(adx=14.0)
        vote_params = self._vote_params_custom(adx_gate=15.0)
        html = _render_trace_vote(scalars, signal=0, vote_params=vote_params)
        # gate text is HTML-escaped
        assert '&gt;= 15' in html, (
            '587b6f0: custom adx_gate=15.0 must appear in gate text; '
            'got default 25.0 instead — locality discipline broken'
        )
        assert '&gt;= 25' not in html

    def test_trace_renders_without_vote_params_key(self) -> None:
        '''_render_trace_panels with a sig_dict that lacks vote_params key does
        not crash and renders the Vote panel.

        This is the end-to-end shape that bb780af handles: old state.json rows
        written before 587b6f0 persisted vote_params. The _render_trace_panels
        wrapper passes vote_params=None to _render_trace_vote when the key is
        absent.
        '''
        scalars = self._scalars_with(adx=30.0, mom1=0.03, mom3=0.03, mom12=0.03)
        sig_dict = {
            'signal': 1,
            'ohlc_window': [],
            'indicator_scalars': scalars,
            # NOTE: no 'vote_params' key — stale pre-587b6f0 shape
        }
        html = _render_trace_panels(sig_dict, 'SPI200', '')
        assert 'ADX gate' in html, (
            'bb780af: _render_trace_panels with no vote_params key must still '
            'render the ADX gate row without crashing'
        )
        assert 'Vote:' in html, (
            'bb780af: Vote panel must render even for stale state rows'
        )
