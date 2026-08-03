# Apply remaining hook agent + video service edits (if not already in commit)

## agent.py

1. Add import:
```python
from app.agents.short_script_agent.hook_utils import strengthen_hook, EXTRA_LEAK_PATTERNS
```

2. Extend `_INSTRUCTION_LEAK_PATTERNS` with:
```python
    *EXTRA_LEAK_PATTERNS,
```

3. After `full_script = _strip_instruction_leaks(full_script)` (or the if/else that sets full_script), add:
```python
        hook = strengthen_hook(hook, full_script)
```

## service.py

Replace the `hook_text=script.seo_title or output.title` argument with:

```python
            hook_text=(
                (getattr(script, "hook", None) or "").strip()
                or script.seo_title
                or output.title
            ),
```
