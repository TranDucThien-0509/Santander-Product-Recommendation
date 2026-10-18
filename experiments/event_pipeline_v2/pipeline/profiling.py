"""Wall time and sampled process RSS, including native model allocations."""
import threading
import time
import psutil


class Profile:
    def __enter__(self):
        self.started = time.perf_counter()
        self.stop = threading.Event()
        self.peak = 0
        self.process = psutil.Process()
        self.sample()
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        self.peak = max(self.peak, self.process.memory_info().rss)

    def watch(self):
        while not self.stop.wait(0.1):
            self.sample()

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()
        self.sample()
        self.result = dict(wall_seconds=time.perf_counter() - self.started,
                           peak_process_rss_mb=self.peak / 1024**2,
                           rss_sampling_interval_seconds=0.1)
