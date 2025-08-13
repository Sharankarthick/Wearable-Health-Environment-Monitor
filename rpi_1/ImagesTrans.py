import os
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SOURCE_DIR = "images"
DEST_IP = "192.168.58.37"
DEST_USER = "ecelab5"
DEST_DIR = "/home/ecelab5/Desktop/smart_health/images"

class ImageHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(('.jpg', '.png', '.jpeg')):
            return
        
        time.sleep(0.5)  # Wait to ensure the image is fully saved

        filename = os.path.basename(event.src_path)
        destination = f"{DEST_USER}@{DEST_IP}:{DEST_DIR}/{filename}"

        result = subprocess.run(["scp", event.src_path, destination])
        
        if result.returncode == 0:
            print(f"? Transferred: {filename}")
        else:
            print(f"? Failed to transfer: {filename}")

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(ImageHandler(), path=SOURCE_DIR, recursive=False)
    observer.start()
    print("?? Watching for new images...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
