"""
Settings management utilities for ArcticDB configuration
"""
from typing import Dict, Any, Optional
import pandas as pd


class SettingsManager:
    def __init__(self, arctic_client):
        print(f"SettingsManager.__init__ called with arctic_client: {arctic_client}")
        self.ac = arctic_client
        
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from ArcticDB general library - EXACT copy from old settings_window.py"""
        print("SettingsManager.load_settings called")
        try:
            lib = self.ac.get_library("general")
            
            if not lib.has_symbol("settings"):
                print("Settings symbol not found, returning defaults")
                return self._get_default_settings()
            
            # Read settings DataFrame - EXACT same as old code
            df = lib.read("settings").data
            settings_dict = df.to_dict()
            
            print(f"Settings loaded successfully: {settings_dict['Value']}")
            return settings_dict['Value']
                
        except Exception as e:
            print(f"Error loading settings: {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_settings()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save all settings to ArcticDB general library - EXACT copy from old settings_window.py"""
        print(f"SettingsManager.save_settings called with: {settings}")
        try:
            # Convert dictionary to DataFrame - EXACT same as old code
            settings_df = pd.DataFrame.from_dict(settings, orient='index', columns=['Value'])
            print(f"Created DataFrame: {settings_df}")
            # Write settings to Arctic - EXACT same as old code
            lib = self.ac.get_library("general")
            print(f"Got general library: {lib}")
            lib.write("settings", settings_df)
            
            print("Settings saved successfully")
            return True
                
        except Exception as e:
            print(f"Error saving settings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_default_settings_df(self, general_lib, defaults: Dict[str, Any]):
        """Create default settings DataFrame in ArcticDB with proper structure"""
        try:
            # Create DataFrame with explicit structure to avoid protobuf crash
            settings_df = pd.DataFrame(
                data=[[value] for value in defaults.values()],
                index=list(defaults.keys()),
                columns=['Value']
            )
            print(f"Creating default settings DataFrame: {settings_df}")
            general_lib.write("settings", settings_df)
            print("Default settings written successfully")
        except Exception as e:
            print(f"Failed to write default settings: {e}")
            raise e
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Return default settings dictionary"""
        return {
            'ib_port': '7497',
            'ib_host': '127.0.0.1',
            's3_db_management': 'False',
            'aws_access_id': '',
            'aws_access_key': '',
            'bucket_name': '',
            'region': '',
            'auto_start_tws': 'False',
            'username': '',
            'password': ''
        }