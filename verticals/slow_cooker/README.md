# Slow Cooker Vertical

This directory is the isolated working tree for Recipe Intelligence's Slow Cooker production population.

The workflow executes the shared Python engine with this directory as its current working directory. Consequently, all relative `data/`, `output/`, and `docs/` paths are Slow Cooker-local and cannot collide with the repository-root Air Fryer state.

Configuration lives under `../../config/verticals/slow_cooker/`.

Do not copy Air Fryer `state.json`, observations, rankings, calibration history, or serving snapshots into this tree. Shared code is intentional; shared mutable ranking state is not.
