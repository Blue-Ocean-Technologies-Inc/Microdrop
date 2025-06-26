from itertools import permutations
import sys
import os
import pytest

def permute(lst):
    return list(permutations(lst))

@pytest.fixture
def Route():
    from device_viewer.models.route import Route
    return Route

# -------------------------
# Route.remove_segment()
# -------------------------

def test_remove_path(Route): # Output is a path
    route = Route([1,2,3,2,4,5,6,2])
    assert route.remove_segment(2,3) == [[1,2,4,5,6,2]]

def test_remove_loop(Route): # Output is a loop
    route = Route([1,2,3,2,4,1])
    assert route.remove_segment(2,3) == [[1,2,4,1]]

def test_remove_cycle_merge(Route): # Requires a merge from the last route to the first route
    route = Route([1,2,3,4,2,3,5,1])
    assert tuple(route.remove_segment(2,3)) in permute([[3,4,2], [3,5,1,2]])

def test_remove_single_segment(Route): # Single segment removed
    route = Route([1,2])
    assert route.remove_segment(1,2) == []

def test_remove_two_cycles(Route): # Result is 2 cycles
    route = Route([1,2,3,4,5,4,3,1])
    assert tuple(route.remove_segment(3,4)) in permute([[4,5,4], [1,2,3,1]])

def test_remove_multiple_passes(Route):
    route = Route([1,2,1,3,1,2,1,4,1,2,1,5,1])
    assert route.remove_segment(1,2) == [[1,3,1,4,1,5,1]]