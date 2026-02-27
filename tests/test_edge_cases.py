"""Edge case tests."""
import pytest
import pandas as pd

def test_empty_data():
    df = pd.DataFrame()
    assert len(df) == 0

def test_valid_data():
    df = pd.DataFrame({'col': [1, 2, 3]})
    assert len(df) == 3
