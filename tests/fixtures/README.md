# Test fixtures

- `headers/`: the exact header rows PresentMon 2.6.0 writes with default options, with
  `--v2_metrics` and with `--v1_metrics`. The default header is copied from a real capture on
  Windows 11; the other two come from `PresentMon/CsvOutput.cpp` at tag `v2.6.0` with its default
  millisecond time unit. All column names were checked against the strings in the released exe.
- Planned: real captures from `tools/probe_presentmon.py` (the `-target.csv` files, trimmed),
  and the CS2 VProf before/after runs (7700 vs 7800X3D) as the reference case for bottleneck
  detection.
