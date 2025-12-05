from shapely import LineString, Polygon

from microdrop_utils.shapely_helpers import sort_polygon_indices_along_line


def test_sort_polygon_indices_along_line():
    """
    Tests that polygons are correctly sorted based on their position along a horizontal line.
    """
    # 1. Setup: Create a horizontal line from x=0 to x=20
    line = LineString([(0, 0), (20, 0)])

    # 2. Setup: Create 3 Polygons placed along the line at x=2, x=10, x=18
    # Polygon 0 (Start)
    poly_start = Polygon([(1, -1), (3, -1), (3, 1), (1, 1)])
    # Polygon 1 (Middle)
    poly_mid = Polygon([(9, -1), (11, -1), (11, 1), (9, 1)])
    # Polygon 2 (End)
    poly_end = Polygon([(17, -1), (19, -1), (19, 1), (17, 1)])

    all_polygons = [poly_start, poly_mid, poly_end]

    # 3. Define indices in a scrambled order (End, Start, Mid)
    scrambled_indices = [2, 0, 1]

    # 4. Execute the sort function
    sorted_result = sort_polygon_indices_along_line(line, all_polygons, scrambled_indices)

    # 5. Assert: The result should be [0, 1, 2] corresponding to Start -> Middle -> End
    assert sorted_result == [0, 1, 2]


def test_sort_polygon_indices_vertical_line():
    """
    Tests sorting along a vertical line to ensure projection works for Y-axis.
    """
    # Vertical line going UP
    line = LineString([(0, 0), (0, 10)])

    # Bottom square (Index 0)
    p1 = Polygon([(-1, 1), (1, 1), (1, 3), (-1, 3)])
    # Top square (Index 1)
    p2 = Polygon([(-1, 7), (1, 7), (1, 9), (-1, 9)])

    polygons = [p1, p2]

    # Pass in reverse order
    indices = [1, 0]

    result = sort_polygon_indices_along_line(line, polygons, indices)

    # Should be sorted bottom-to-top [0, 1]
    assert result == [0, 1]