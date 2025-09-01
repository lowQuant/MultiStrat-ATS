"""
Settings API routes
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, TYPE_CHECKING
from core.arctic_manager import test_aws_s3_connection
import pandas as pd

if TYPE_CHECKING:
    from core.strategy_manager import StrategyManager

# Create router for settings endpoints
router = APIRouter(prefix="/api/settings", tags=["settings"])

# This will be injected by main.py
strategy_manager = None

def set_strategy_manager(sm: "StrategyManager"):
    """Set the strategy manager instance"""
    global strategy_manager
    strategy_manager = sm


class SettingsRequest(BaseModel):
    ib_port: str = "7497"
    ib_host: str = "127.0.0.1"
    s3_db_management: str = "False"
    aws_access_id: str = ""
    aws_access_key: str = ""
    bucket_name: str = ""
    region: str = ""
    auto_start_tws: str = "False"
    username: str = ""
    password: str = ""


# ----- Internal helpers (single-module persistence) -----
def _default_settings() -> Dict[str, Any]:
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


def _write_settings(ac, settings: Dict[str, Any]) -> None:
    lib = ac.get_library('general')
    # Build a well-formed single-column DataFrame with index as keys
    settings_df = pd.DataFrame(
        data=[[v] for v in settings.values()],
        index=list(settings.keys()),
        columns=['Value']
    )
    lib.write('settings', settings_df)


def _read_settings(ac) -> Dict[str, Any]:
    lib = ac.get_library('general')
    if not lib.has_symbol('settings'):
        # Initialize with defaults to ensure consistent schema
        _write_settings(ac, _default_settings())
    df = lib.read('settings').data
    # Expect a single column 'Value'; fall back to first column if needed
    if 'Value' in df.columns:
        return df['Value'].to_dict()
    else:
        return df.iloc[:, 0].to_dict()


@router.get("/")
async def get_settings():
    """Get current settings from file"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        # Use lazy ArcticDB client access
        ac = strategy_manager.ac if strategy_manager.ac is not None else strategy_manager.get_arctic_client()
        settings = _read_settings(ac)
        
        return {
            "success": True,
            "settings": settings
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/")
async def save_settings(settings_request: SettingsRequest):
    """Save settings to file"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    print("print from routes/settings.py post/")

    print(settings_request)
    try:
        # Test S3 connection if S3 is enabled
        if settings_request.s3_db_management == "True":
            if not all([settings_request.aws_access_id, settings_request.aws_access_key, 
                       settings_request.bucket_name, settings_request.region]):
                return {
                    "success": False,
                    "error": "Please fill all AWS S3 credentials"
                }
            
            # Test S3 connection before saving
            s3_test_result = test_aws_s3_connection(
                settings_request.aws_access_id,
                settings_request.aws_access_key,
                settings_request.bucket_name,
                settings_request.region
            )
            
            if not s3_test_result:
                return {
                    "success": False,
                    "error": "S3 connection test failed. Please check your credentials"
                }
        
        # Prefer injected ArcticDB client; fall back to lazy getter
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        
        # Convert Pydantic model to dictionary
        settings_dict = settings_request.dict()
        print("###############################")
        print(settings_dict)
        print("###############################")
        _write_settings(ac, settings_dict)
        success = True
        
        if success:
            return {
                "success": True,
                "message": "Settings saved successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to save settings"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test-s3")
async def test_s3_connection(
    aws_access_id: str,
    aws_access_key: str,
    bucket_name: str,
    region: str
):
    """Test AWS S3 connection"""
    try:
        result = test_aws_s3_connection(aws_access_id, aws_access_key, bucket_name, region)
        
        if result:
            return {
                "success": True,
                "message": "S3 connection test successful"
            }
        else:
            return {
                "success": False,
                "error": "S3 connection test failed"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/{setting_key}")
async def get_setting(setting_key: str):
    """Get a specific setting value"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        settings = _read_settings(ac)
        value = settings.get(setting_key)
        
        if value is not None:
            return {
                "success": True,
                "key": setting_key,
                "value": value
            }
        else:
            return {
                "success": False,
                "error": f"Setting '{setting_key}' not found"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.put("/{setting_key}")
async def update_setting(setting_key: str, value: str):
    """Update a specific setting"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        settings = _read_settings(ac)
        settings[setting_key] = value
        _write_settings(ac, settings)
        success = True
        
        if success:
            return {
                "success": True,
                "message": f"Setting '{setting_key}' updated successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to update setting '{setting_key}'"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}
