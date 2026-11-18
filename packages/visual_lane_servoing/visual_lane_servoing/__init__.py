import os as _os

# The student code lives in `../include/` (importable as `visual_lane_servoing.include`, the same
# name the notebooks use). With a colcon symlink-install this regular package shadows the plain
# directory, so the package root is added to the search path explicitly.
__path__.append(_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__))))
