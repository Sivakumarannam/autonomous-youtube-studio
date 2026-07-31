from gradio_client import Client
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

print("Creating client...")
client = Client("kevinwang676/SadTalker")
print("Client created.")

print("Submitting job...")

job = client.submit(
    "storage/avatars/female_presenter.png",
    "test_audio.wav",
    "full",
    True,
    False,
    1,
    "256",
    0,
    fn_index=0,
)

print("Job submitted.")

while not job.done():
    try:
        print("Status:", job.status())
    except Exception as e:
        print("Couldn't get status:", e)
    time.sleep(5)

print("\nJob finished!")
print(job.result())