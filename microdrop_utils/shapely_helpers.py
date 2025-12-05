from shapely.geometry import LineString, Polygon


def get_polygon_distance_from_line_start(target_polygon: 'Polygon', target_line: 'LineString'):
    # Calculate the geometric intersection between the polygon and the line.
    # Returns LineString = segment of line inside polygon.
    intersection_geometry = target_polygon.intersection(target_line)

    if intersection_geometry.is_empty:
        # Handle edge case where polygon doesn't actually intersect
        raise ValueError("No intersection found: Provide intersecting polygons")

    # Find intersection geometry center point
    # This reduces the intersection segment to a single Point that we can measure.
    intersection_center = intersection_geometry.centroid

    # Project that point onto the original line.
    # line.project(point) calculates the distance from the start of the line
    # (index 0.0) to the point nearest to the centroid.
    distance_from_start = target_line.project(intersection_center)

    return distance_from_start

def sort_polygon_indices_along_line(line: LineString, polygons: list[Polygon], indices: list[int]) -> list[int]:
    """
    Sorts a list of polygon indices based on the spatial order of their intersection
    along a specific line.

    This function determines the order by finding the intersection between the line
    and each polygon, calculating the centroid of that intersection, and measuring
    how far along the line that centroid falls.

    Args:
        line (LineString): The reference line (e.g., a connecting trace).
        polygons (list[Polygon]): The master list of all polygon objects.
        indices (list[int]): A list of integers pointing to specific polygons
                             in the 'polygons' list that intersect the line.

    Returns:
        list[int]: A new list of indices sorted from the start of the line to the end.
    """

    def _get_distance_along_line(poly_idx):
        return get_polygon_distance_from_line_start(polygons[poly_idx], line)

    # Sort the list of indices using the calculated distance of polygons from line start as the key.
    sorted_indices = sorted(indices, key=_get_distance_along_line)

    return sorted_indices


if __name__ == "__main__":
    from matplotlib import pyplot as plt
    # ==============================================================================
    # VISUALIZATION SCRIPT
    # This block creates sample data, runs the sort, and visualizes the result
    # using Matplotlib.
    # ==============================================================================

    # 1. Setup Data
    # Create a diagonal line from (0,0) to (20,20)
    line = LineString([(0, 0), (20, 20)])

    # Create 3 Polygons placed along the line.
    # We add them to the list in a scrambled spatial order.

    # Polygon A (Middle) -> Index 0
    poly_mid = Polygon([(9, 9), (11, 9), (11, 11), (9, 11)])

    # Polygon B (Start) -> Index 1
    poly_start = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])

    # Polygon C (End) -> Index 2
    poly_end = Polygon([(17, 17), (19, 17), (19, 19), (17, 19)])

    all_polygons = [poly_mid, poly_start, poly_end]

    # The indices we want to sort (currently 0=Mid, 1=Start, 2=End)
    indices_to_sort = [0, 1, 2]

    print(f"Original Indices: {indices_to_sort}")

    # 2. Run the Sorting Function
    sorted_result = sort_polygon_indices_along_line(line, all_polygons, indices_to_sort)

    print(f"Sorted Indices:   {sorted_result}")
    # We expect [1, 0, 2] because Index 1 is Start, Index 0 is Mid, Index 2 is End.

    # 3. Visualize with Matplotlib
    fig, ax = plt.subplots(figsize=(8, 8))

    # Plot the Line
    lx, ly = line.xy
    ax.plot(lx, ly, color='blue', linewidth=2, label='Reference Line', linestyle='--')
    ax.plot(lx[0], ly[0], 'o', color='blue', label='Start of Line')

    # Plot the Polygons
    colors = ['orange', 'green', 'red']
    for i, poly in enumerate(all_polygons):
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0.5, fc=colors[i], ec='black', label=f'Poly Index {i}')

        # Label the Polygon Index inside the shape
        c = poly.centroid
        ax.text(c.x, c.y, f"ID: {i}", fontsize=12, ha='center', va='center',
                fontweight='bold', color='white')

    # Annotate the Resulting Rank
    for rank, idx in enumerate(sorted_result):
        poly = all_polygons[idx]
        # Place a rank label slightly above the polygon
        x, y = poly.exterior.xy
        top_y = max(y)
        mid_x = (min(x) + max(x)) / 2
        ax.text(mid_x, top_y + 0.8, f"Rank: {rank}", ha='center', color='black',
                fontsize=10, fontweight='bold')

    ax.set_title(f"Polygon Sorting Visualization\nResult: {sorted_result}")
    ax.set_xlabel("X Coordinate")
    ax.set_ylabel("Y Coordinate")
    ax.legend(loc='lower right')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.set_aspect('equal')

    print("Displaying plot...")
    plt.show()