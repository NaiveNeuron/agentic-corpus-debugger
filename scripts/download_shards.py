"""Download the Slovak FineWeb2 parquet shards from the Hugging Face Hub."""
import sys
from huggingface_hub import snapshot_download

def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 204
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    idx = list(range(0, 204, step))[:n]
    pats = [f"data/train-{i:05d}-of-00204.parquet" for i in idx]
    print(f"downloading {len(pats)} shards", flush=True)
    path = snapshot_download(
        "ivykopal/fineweb2-slovak", repo_type="dataset",
        allow_patterns=pats, local_dir="data/hf", max_workers=12,
    )
    print("done", path, flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
