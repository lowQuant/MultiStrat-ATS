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
    
    # Default paths to check (adjust based on your actual paths)
    default_paths = [
        "ARCTICDB",  # Current project structure
        "../ARCTICDB",
        os.path.join(os.getcwd(), "ARCTICDB"),
        os.path.join(Path(__file__).parent.parent.parent, "ARCTICDB")
    ]
    
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
        default_path = "ARCTICDB"
        os.makedirs(default_path, exist_ok=True)
        ac_local = Arctic(f'lmdb://{default_path}?map_size=50MB')
        add_log(f"Created new ArcticDB at {default_path}", "ARCTIC")

    # Create library options with dynamic schema
    library_options = LibraryOptions(dynamic_schema=True)

    # Create required libraries
    libraries_to_create = {
        'general': 'Settings and strategy metadata',
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
                ac_local.get_library(lib_name, create_if_missing=True)

    # Initialize default settings if they don't exist
    general_lib = ac_local.get_library('general')
    if not general_lib.has_symbol("settings"):
        add_log("Creating default settings", "ARCTIC")
        settings_data = {
            'Value': [
                "7497",      # IB port
                "127.0.0.1", # IB host
                "False",     # S3 management
                "",          # AWS access ID
                "",          # AWS secret key
                "",          # S3 bucket
                "us-east-1", # AWS region
                "False",     # Auto-start TWS
                "",          # Username
                ""           # Password
            ]
        }
        
        index_values = [
            'ib_port', 'ib_host', 's3_db_management',
            'aws_access_id', 'aws_access_key', 'bucket_name', 'region',
            'start_tws', 'username', 'password'
        ]
        
        settings_df = pd.DataFrame(settings_data, index=index_values)
        general_lib.write("settings", settings_df)

    return ac_local


# Global instance
_arctic_connection = None

def get_ac(db_path: Optional[str] = None) -> Arctic:
    """
    Get the global ArcticDB connection instance.
    Follows the pattern from the original project.
    
    Args:
        db_path: Optional custom path to the Arctic database
        
    Returns:
        Arctic connection instance
    """
    global _arctic_connection
    if _arctic_connection is None:
        _arctic_connection = initialize_db(db_path)
    return _arctic_connection
