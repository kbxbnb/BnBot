import time
from pipeline import run_pipeline_once
import db_bootstrap  # executes and creates tables on import

if __name__ == "__main__":
    print("🚀 BnBot pipeline running every 10 seconds")
    while True:
        try:
            run_pipeline_once()
        except Exception as e:
            print(f"❌ Pipeline error: {e}")
        time.sleep(10)
