# Hook fixes on main (applied)

## Already committed on main
- `app/agents/short_script_agent/prompts.py` — banned weak openers, stronger hooks
- `app/agents/quality_agent/prompts.py` — harder engagement scoring
- `app/agents/short_script_agent/hook_utils.py` — `strengthen_hook`
- `app/agents/short_script_agent/agent.py` — uses `strengthen_hook` after LLM parse
- `app/agents/video_agent/video_hook_bootstrap.py` — prefers `script.hook` for overlay

## One-time: wire bootstrap in `app/main.py`

Right after `logger.info("Database ready")` add:

```python
    from app.agents.video_agent.video_hook_bootstrap import apply_video_hook_overlay_patch
    apply_video_hook_overlay_patch()

    try:
        from app.core.low_ram_bootstrap import apply_low_ram_patches
        apply_low_ram_patches()
    except Exception:
        pass
```

Or run on the VM after `git pull`:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app/main.py")
t = p.read_text()
needle = '    logger.info("Database ready")\n'
insert = needle + '''
    from app.agents.video_agent.video_hook_bootstrap import apply_video_hook_overlay_patch
    apply_video_hook_overlay_patch()

    try:
        from app.core.low_ram_bootstrap import apply_low_ram_patches
        apply_low_ram_patches()
    except Exception:
        pass
'''
if "apply_video_hook_overlay_patch" not in t:
    assert needle in t, "needle not found"
    p.write_text(t.replace(needle, insert, 1))
    print("main.py patched")
else:
    print("already patched")
PY
