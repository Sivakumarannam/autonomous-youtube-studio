# Step 3 — Caption edge clip (on main)

Files:
- `app/agents/video_agent/caption_bar.py`
- `app/agents/video_agent/caption_clip_bootstrap.py`

## Wire once in `app/main.py`

After `logger.info("Database ready")` (near your other patches), add:

```python
    from app.agents.video_agent.caption_clip_bootstrap import apply_caption_clip_patch
    apply_caption_clip_patch()
```

Or run on the VM after `git pull`:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app/main.py")
t = p.read_text()
needle = '    apply_video_hook_overlay_patch()\n'
insert = needle + '''
    from app.agents.video_agent.caption_clip_bootstrap import apply_caption_clip_patch
    apply_caption_clip_patch()
'''
if "apply_caption_clip_patch" not in t:
    if needle in t:
        p.write_text(t.replace(needle, insert, 1))
        print("main.py patched (after hook)")
    else:
        needle2 = '    logger.info("Database ready")\n'
        insert2 = needle2 + '''
    from app.agents.video_agent.caption_clip_bootstrap import apply_caption_clip_patch
    apply_caption_clip_patch()
'''
        assert needle2 in t
        p.write_text(t.replace(needle2, insert2, 1))
        print("main.py patched (after Database ready)")
else:
    print("already patched")
PY
```

Rebuild, run **one** Short, confirm captions do not touch left/right edges.
