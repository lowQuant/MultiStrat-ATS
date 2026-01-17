"""
Simple ArcticDB connection manager for IB Multi-Strategy ATS
Based on the original backend_old/data_and_research/utils.py design
"""
import os
import pandas as pd
from pathlib import Path
from arcticdb import Arctic, LibraryOptions
try:
    # Available in ArcticDB >= 5.x
    from arcticdb import defragment_symbol_data, QueryBuilder  # type: ignore
except Exception:
    def defragment_symbol_data(*args, **kwargs):  # fallback no-op
        return

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
        # Always initialize local first
        ac_local = initialize_db(db_path)

        # Try to read settings from local 'general/settings' to see if S3 is enabled
        try:
            lib = ac_local.get_library('general')
            if lib.has_symbol('settings'):
                df = lib.read('settings').data
                # Normalize to a single 'Value' series regardless of schema
                series = df['Value'] if 'Value' in df.columns else df.iloc[:, 0]

                def _as_bool(v) -> bool:
                    return str(v).strip().lower() in {"true", "1", "yes", "y"}

                if _as_bool(series.get('s3_db_management', 'False')):
                    region = str(series.get('region', '')).strip()
                    bucket = str(series.get('bucket_name', '')).strip()
                    access = str(series.get('aws_access_id', '')).strip()
                    secret = str(series.get('aws_access_key', '')).strip()

                    if region and bucket and access and secret:
                        try:
                            connection_string = (
                                f's3://s3.{region}.amazonaws.com:{bucket}?region={region}&access={access}&secret={secret}'
                            )
                            ac_s3 = Arctic(connection_string)

                            # Ensure S3 'general' library exists and carries 'settings'
                            if 'general' not in ac_s3.list_libraries():
                                ac_s3.get_library('general', create_if_missing=True, library_options=LibraryOptions(dynamic_schema=True))
                            lib_s3 = ac_s3.get_library('general')
                            if not lib_s3.has_symbol('settings'):
                                lib_s3.write('settings', df)

                            add_log(f"Connected to ArcticDB S3 bucket '{bucket}' in region '{region}'", "ARCTIC")
                            _arctic_connection = ac_s3
                            return _arctic_connection
                        except Exception as s3e:
                            add_log(f"Falling back to local ArcticDB (S3 connect failed: {s3e})", "ARCTIC",)
        except Exception as e:
            # Any issue reading settings: keep using local
            add_log(f"Using local ArcticDB (settings read failed: {e})", "ARCTIC")

        # Default to local if S3 not enabled or any failure above
        _arctic_connection = ac_local
    return _arctic_connection

def defragment_account_portfolio(library, symbol="portfolio") -> None:
    """
    Defragment the account-level 'portfolio' symbol stored in the
    account_id library, if present. Safe no-op on errors.
    """
    try:
        if not library:
            return
        # The symbol name is 'portfolio' as per architecture.md
        if symbol in library.list_symbols():
            defragment_symbol_data(library, symbol)
            print(f"Defragmented '{symbol}' in account library '{library.name}'")
    except Exception as e:
        # Never block initialization due to maintenance
        print(f"Defragmentation skipped for account '{library.name}': {e}")

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
