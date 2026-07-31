from gradio_client import Client
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


print("Creating client...")

client = Client("kevinwang676/SadTalker")

print("Connected!")

print(client.view_api())