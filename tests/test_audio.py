import numpy as np
import pytest

from wordcaps.audio import auto_threshold, rms_db, speech_blocks

SR = 16000


def signal(parts):
    """parts: list of (seconds, amplitude)."""
    out = []
    t0 = 0
    for dur, amp in parts:
        n = int(dur * SR)
        t = (np.arange(n) + t0) / SR
        out.append(amp * np.sin(2 * np.pi * 220 * t))
        t0 += n
    return np.concatenate(out)


def test_rms_db_levels():
    db = rms_db(signal([(0.5, 0.0), (0.5, 0.5)]), SR, hop=0.05)
    assert len(db) == 20
    assert db[:10].max() < -100          # digital silence
    assert db[10:] == pytest.approx(20 * np.log10(0.5 / np.sqrt(2)), abs=0.1)


def test_rms_db_short_input():
    assert len(rms_db(np.zeros(10), SR, hop=0.05)) == 0


def test_speech_blocks_merges_short_gaps_and_drops_blips():
    x = signal([(0.5, 0), (1.0, 0.3), (0.1, 0), (0.5, 0.3), (1.0, 0), (0.05, 0.3), (0.5, 0)])
    blocks = speech_blocks(rms_db(x, SR), 0.05, threshold=-32)
    # the 0.1 s dip is bridged, the 0.05 s blip is dropped
    assert blocks == [(0.5, 2.1)]


def test_speech_blocks_keeps_long_gaps():
    x = signal([(0.2, 0), (0.5, 0.3), (0.6, 0), (0.5, 0.3)])
    assert speech_blocks(rms_db(x, SR), 0.05, threshold=-32) == [(0.2, 0.7), (1.3, 1.8)]


def test_auto_threshold_sits_between_floor_and_speech():
    x = signal([(1.0, 0.001), (1.0, 0.3), (1.0, 0.001)])
    db = rms_db(x, SR)
    thr = auto_threshold(db)
    assert db.min() < thr < db.max()
    assert speech_blocks(db, 0.05, threshold=None) == [(1.0, 2.0)]
