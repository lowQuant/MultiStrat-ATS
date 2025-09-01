"""
Simple ArcticDB connection manager for IB Multi-Strategy ATS
Based on the original backend_old/data_and_research/utils.py design
"""
import os
import pandas as pd
from pathlib import Path
from arcticdb import Arctic, LibraryOptions
from typing import Optional

from .log_manager import add_log

def initialize_db(db_path: Optional[str] = None) -> Arctic:
    """
    Initialize ArcticDB connection with fallback paths.
    Based on the original utils.py initialize_db function.
    
    Args:
        db_path: Optional custom path to the Arctic database
        
    Returns:
        Arctic connection instance
    """
    
    # Use fixed path under backend/ArcticDB
    backend_dir = Path(__file__).parent.parent
    target_path = backend_dir / "ArcticDB"
    default_paths = [str(target_path)]
    
    # Use the provided db_path or find a default path
    if db_path:
        db_paths = [db_path]
    else:
        db_paths = default_paths
    
    for path in db_paths:
        if os.path.exists(path):
            ac_local = Arctic(f'lmdb://{path}?map_size=50MB')
            add_log(f"Connected to ArcticDB at {path}", "ARCTIC")
            break
    else:
        # Create default path if none exists
        default_path = str(target_path)
        os.makedirs(default_path, exist_ok=True)
        ac_local = Arctic(f'lmdb://{default_path}?map_size=50MB')
        add_log(f"Created new ArcticDB at {default_path}", "ARCTIC")

    # Create library options with dynamic schema
    library_options = LibraryOptions(dynamic_schema=True)

    # Create required libraries
    libraries_to_create = {
        'general': 'Settings',
        'strategies': 'Strategy metadata',
        'portfolio': 'Strategy positions and portfolio data', 
        'pnl': 'Strategy and account P&L tracking',
        'market_data': 'Historical and real-time market data'
    }
    
    for lib_name, description in libraries_to_create.items():
        if lib_name not in ac_local.list_libraries():
            add_log(f"Creating library '{lib_name}': {description}", "ARCTIC")
            if lib_name == 'portfolio':
                # Portfolio needs dynamic schema for flexible position data
                ac_local.get_library(lib_name, create_if_missing=True, library_options=library_options)
            else:
                ac_local.get_library(lib_name, create_if_missing=True, library_options=library_options)

    # Don't create default settings during initialization to avoid protobuf crash
    # Settings will be created lazily when first accessed by SettingsManager

    return ac_local


# Global instance
_arctic_connection = None

def get_ac(db_path: Optional[str] = None) -> Arctic:
    """Get ArcticDB client instance"""
    global _arctic_connection
    if _arctic_connection is None:
        _arctic_connection = initialize_db(db_path)
    return _arctic_connection


class ArcticManager:
    """Wrapper class for ArcticDB operations"""
    
    def __init__(self):
        self.client = None
    
    def get_client(self, db_path: Optional[str] = None) -> Arctic:
        """Get or create ArcticDB client"""
        if self.client is None:
            self.client = initialize_db(db_path)
        return self.client

def test_aws_s3_connection(aws_access_id: str, aws_access_key: str, bucket_name: str, region: str) -> bool:
    """Test AWS S3 connection for ArcticDB"""
    try:
        from arcticdb import Arctic
        
        # Create connection string like the old implementation
        connection_string = f's3://s3.{region}.amazonaws.com:{bucket_name}?region={region}&access={aws_access_id}&secret={aws_access_key}'
        print(f"Testing S3 connection with: s3://s3.{region}.amazonaws.com:{bucket_name}")
        
        # Test connection by creating and deleting a test library
        test_connection = Arctic(connection_string)
        
        try:
            # Try to create a test library
            test_connection.create_library('test_connection')
            print("Test library created successfully")
            
            # Clean up by deleting the test library
            test_connection.delete_library('test_connection')
            print("Test library deleted successfully")
            
            return True
            
        except Exception as lib_error:
            print(f"Library operation failed: {lib_error}")
            return False
            
    except Exception as e:
        print(f"Failed to connect to AWS S3: {e}")
        return False
