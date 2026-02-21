"""
Unit tests for app.core.serializers
Tests NumPy type conversion, Pandas object serialization, and Large Integer handling for FastAPI responses.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from unittest.mock import MagicMock, patch

from app.core.serializers import (
    ensure_json_serializable,
    convert_large_ints_to_str,
    prepare_response,
    dataframe_to_response,
    auto_serialize
)

class TestEnum(Enum):
    VALUE1 = "val1"
    VALUE2 = "val2"

def test_ensure_json_serializable_basic():
    """Test basic types pass through."""
    assert ensure_json_serializable(None) is None
    assert ensure_json_serializable(1) == 1
    assert ensure_json_serializable("test") == "test"
    assert ensure_json_serializable(True) is True

def test_ensure_json_serializable_numpy_integers():
    """Test various NumPy integer types conversion."""
    assert ensure_json_serializable(np.int64(123)) == 123
    assert ensure_json_serializable(np.int32(456)) == 456
    assert ensure_json_serializable(np.uint64(789)) == 789
    assert isinstance(ensure_json_serializable(np.int64(123)), int)

def test_ensure_json_serializable_numpy_floats():
    """Test NumPy float types and NaN/Inf handling."""
    assert ensure_json_serializable(np.float64(123.45)) == 123.45
    assert isinstance(ensure_json_serializable(np.float64(123.45)), float)
    
    # Test NaN and Inf
    assert ensure_json_serializable(np.float64(np.nan)) is None
    assert ensure_json_serializable(np.float64(np.inf)) is None
    assert ensure_json_serializable(float('nan')) is None
    assert ensure_json_serializable(float('inf')) is None

def test_ensure_json_serializable_numpy_misc():
    """Test NumPy boolean, datetime64 and ndarray."""
    assert ensure_json_serializable(np.bool_(True)) is True
    assert ensure_json_serializable(np.bool_(False)) is False
    
    # Datetime64
    dt64 = np.datetime64('2023-01-01T12:00:00')
    assert "2023-01-01T12:00:00" in ensure_json_serializable(dt64)
    
    # Array
    arr = np.array([1, 2, 3])
    assert ensure_json_serializable(arr) == [1, 2, 3]

def test_ensure_json_serializable_pandas():
    """Test Pandas Series and DataFrame."""
    s = pd.Series([1, 2], index=['a', 'b'])
    assert ensure_json_serializable(s) == {'a': 1, 'b': 2}
    
    df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4]})
    expected_df = [{'col1': 1, 'col2': 3}, {'col1': 2, 'col2': 4}]
    assert ensure_json_serializable(df) == expected_df

def test_ensure_json_serializable_standard_objects():
    """Test datetime, date, Decimal and Enum."""
    dt = datetime(2023, 1, 1, 12, 0, 0)
    assert ensure_json_serializable(dt) == dt.isoformat()
    
    d = date(2023, 1, 1)
    assert ensure_json_serializable(d) == d.isoformat()
    
    assert ensure_json_serializable(Decimal("123.45")) == 123.45
    assert ensure_json_serializable(TestEnum.VALUE1) == "val1"

def test_ensure_json_serializable_nested():
    """Test nested dictionary and list serialization."""
    data = {
        "a": np.int64(1),
        "b": [np.float64(2.0), {"c": np.bool_(True)}]
    }
    expected = {
        "a": 1,
        "b": [2.0, {"c": True}]
    }
    assert ensure_json_serializable(data) == expected

def test_convert_large_ints_to_str_auto():
    """Test automatic conversion of large integers (> 2^53)."""
    small_int = 2**53 - 1
    large_int = 2**53 + 1
    
    data = {"small": small_int, "large": large_int}
    result = convert_large_ints_to_str(data)
    
    assert result["small"] == small_int
    assert result["large"] == str(large_int)

def test_convert_large_ints_to_str_explicit():
    """Test explicit field conversion."""
    data = {"id": 123, "val": 456}
    result = convert_large_ints_to_str(data, fields=["id"])
    
    assert result["id"] == "123"
    assert result["val"] == 456
    
    # Nested
    data_nested = {"items": [{"id": 789}, {"id": 101}]}
    result_nested = convert_large_ints_to_str(data_nested, fields=["id"])
    assert result_nested["items"][0]["id"] == "789"
    assert result_nested["items"][1]["id"] == "101"

def test_prepare_response():
    """Test the main orchestrator function."""
    data = {
        "contract_id": 9007199254740993, # 2^53 + 1
        "price": np.float64(1.23)
    }
    # Should convert numpy float and large int (if auto-detected or explicit)
    result = prepare_response(data, id_fields=["contract_id"])
    
    assert result["contract_id"] == "9007199254740993"
    assert result["price"] == 1.23
    assert isinstance(result["price"], float)

@pytest.mark.asyncio
async def test_auto_serialize_decorator():
    """Test the auto_serialize decorator."""
    @auto_serialize
    async def mock_endpoint():
        return {"val": np.int64(123)}
    
    result = await mock_endpoint()
    assert result == {"val": 123}
    assert isinstance(result["val"], int)

def test_dataframe_to_response():
    """Test dataframe_to_response convenience function."""
    df = pd.DataFrame({
        "contract_id": [9007199254740993, 123],
        "profit": [np.float64(10.5), np.float64(-2.0)]
    })
    
    result = dataframe_to_response(df, id_fields=["contract_id"])
    
    assert len(result) == 2
    assert result[0]["contract_id"] == "9007199254740993"
    assert result[0]["profit"] == 10.5
    assert result[1]["contract_id"] == "123"
    
    # Empty DF
    assert dataframe_to_response(pd.DataFrame()) == []
