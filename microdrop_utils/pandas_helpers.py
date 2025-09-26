import pandas as pd
import numpy as np
from typing import Union

def map_series_to_array(
    series: pd.Series,
    fill_value: Union[int, float] = np.nan
) -> np.ndarray:
    """Converts a pandas Series to a NumPy array based on the Series' index.

    The function creates a new NumPy array whose size is determined by the
    maximum index value in the input Series. It then places each value from
    the Series into the array at its corresponding index, filling all other
    unspecified indices with a default value.

    Args:
        series: The input pandas Series. The index must be integer-based.
        fill_value: The value to use for array indices not present in the
            Series' index. Defaults to np.nan.

    Returns:
        A NumPy array with the Series' values mapped to their index positions.

    Examples:
        >>> s = pd.Series([10, 20, 30], index=[1, 3, 4], dtype=np.int32)
        >>> map_series_to_array(s, fill_value=0)
        array([ 0, 10,  0, 20, 30], dtype=int32)

        >>> s_float = pd.Series([9.9, 8.8], index=[3, 0], dtype=np.float32)
        >>> map_series_to_array(s_float)
        array([8.8, nan, nan, 9.9], dtype=float32)

        >>> s_empty = pd.Series([], dtype=np.float32)
        >>> map_series_to_array(s_empty)
        array([], dtype=float32)
    """
    # Return an empty array if the input series is empty
    if series.empty:
        return np.array([], dtype=series.dtype)

    # Determine the required size from the maximum index value
    size = series.index.max() + 1

    # Create a new NumPy array filled with the default value
    # The array's data type is inherited from the input series
    numpy_array = np.full(size, fill_value, dtype=series.dtype)

    # Use the Series' index to place the values in the correct positions
    numpy_array[series.index] = series.values

    return numpy_array

# Example of running the doctests
if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)