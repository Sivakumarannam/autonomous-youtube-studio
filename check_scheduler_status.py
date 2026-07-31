import asyncio
from app.scheduler.scheduler import get_last_tick_info

# The scheduler module should have recorded the last tick if it's running
last_tick = get_last_tick_info()

if last_tick:
    print("Scheduler has been running!")
    print(f"Last tick at: {last_tick['ran_at']}")
    print(f"Due count: {last_tick['due_count']}")
    print(f"Succeeded: {last_tick['succeeded']}")
    print(f"Failed: {last_tick['failed']}")
else:
    print("ERROR: Scheduler has NEVER ticked!")
    print("The scheduler is either not running or hasn't completed even one tick yet.")
