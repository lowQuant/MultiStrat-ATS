"""
Emergency script to fix corrupted ArcticDB data
Run this to delete corrupted symbols without losing all data
"""
import os
import shutil
from pathlib import Path

# Path to ArcticDB
backend_dir = Path(__file__).parent
arctic_path = backend_dir / "ArcticDB"

print(f"ArcticDB path: {arctic_path}")
print(f"ArcticDB exists: {arctic_path.exists()}")

if arctic_path.exists():
    print("\n=== Option 1: Backup entire database ===")
    backup_path = backend_dir / "ArcticDB.backup"
    if backup_path.exists():
        print(f"Warning: Backup already exists at {backup_path}")
        print("Delete it first if you want to create a new backup")
    else:
        print(f"To backup, run:")
        print(f"  mv {arctic_path} {backup_path}")
    
    print("\n=== Option 2: Just rename to start fresh ===")
    print(f"  mv {arctic_path} {arctic_path}.old")
    
    print("\n=== Option 3: Delete completely ===")
    print(f"  rm -rf {arctic_path}")
    
    print("\n=== Current DB size ===")
    total_size = sum(f.stat().st_size for f in arctic_path.rglob('*') if f.is_file())
    print(f"  {total_size / (1024*1024):.2f} MB")
    
    print("\n=== Files in ArcticDB ===")
    for item in sorted(arctic_path.rglob('*'))[:20]:  # First 20 items
        if item.is_file():
            size = item.stat().st_size / 1024
            print(f"  {item.relative_to(arctic_path)} ({size:.1f} KB)")
else:
    print("ArcticDB directory does not exist - a fresh one will be created on next run")
