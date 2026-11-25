"""Frame statistics and CPU/GPU bottleneck classification (next step 3).

Uses canonical columns from columns.py only. Frame-time stats come from
ms_between_presents; the bottleneck signal compares ms_gpu_busy with ms_frame_time.
See docs/presentmon.md for the draft rules and the caveats (HAGS, Reflex, FPS caps).
"""
