import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Save, RefreshCw, Database, Server, Cloud, User } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface Settings {
  ib_port: string;
  ib_host: string;
  s3_db_management: string;
  aws_access_id: string;
  aws_access_key: string;
  bucket_name: string;
  region: string;
  auto_start_tws: string;
  username: string;
  password: string;
}

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<Settings>({
    ib_port: '7497',
    ib_host: '127.0.0.1',
    s3_db_management: 'False',
    aws_access_id: '',
    aws_access_key: '',
    bucket_name: '',
    region: '',
    auto_start_tws: 'False',
    username: '',
    password: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const loadSettings = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/api/settings/');
      const data = await response.json();
      
      if (data.success) {
        setSettings(data.settings);
        toast({
          title: "Settings Loaded",
          description: "Settings loaded successfully from ArcticDB",
        });
      } else {
        toast({
          title: "Error",
          description: data.error || "Failed to load settings",
          variant: "destructive",
        });
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to connect to backend",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/api/settings/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });
      
      const data = await response.json();
      
      if (data.success) {
        toast({
          title: "Settings Saved",
          description: "Settings saved successfully to ArcticDB",
        });
      } else {
        toast({
          title: "Error",
          description: data.error || "Failed to save settings",
          variant: "destructive",
        });
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to connect to backend",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleInputChange = (key: keyof Settings, value: string) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleSwitchChange = (key: keyof Settings, checked: boolean) => {
    setSettings(prev => ({
      ...prev,
      [key]: checked ? 'True' : 'False'
    }));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
          <p className="text-muted-foreground">
            Configure your trading system settings
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={loadSettings}
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="grid gap-6">
        {/* Interactive Brokers Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              Interactive Brokers Connection
            </CardTitle>
            <CardDescription>
              Configure connection settings for IB TWS/Gateway
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ib_host">IB Host</Label>
                <Input
                  id="ib_host"
                  value={settings.ib_host}
                  onChange={(e) => handleInputChange('ib_host', e.target.value)}
                  placeholder="127.0.0.1"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ib_port">IB Port</Label>
                <Input
                  id="ib_port"
                  value={settings.ib_port}
                  onChange={(e) => handleInputChange('ib_port', e.target.value)}
                  placeholder="7497"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ArcticDB / S3 Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              ArcticDB Configuration
            </CardTitle>
            <CardDescription>
              Configure database storage settings
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center space-x-2">
              <Switch
                id="s3_management"
                checked={settings.s3_db_management === 'True'}
                onCheckedChange={(checked) => handleSwitchChange('s3_db_management', checked)}
              />
              <Label htmlFor="s3_management">Enable S3 Database Management</Label>
            </div>
            
            <Separator />
            
            <div className="space-y-4">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <Cloud className="h-4 w-4" />
                AWS S3 Configuration
              </h4>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="aws_access_id">AWS Access ID</Label>
                  <Input
                    id="aws_access_id"
                    type="password"
                    value={settings.aws_access_id}
                    onChange={(e) => handleInputChange('aws_access_id', e.target.value)}
                    placeholder="Enter AWS Access Key ID"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="aws_access_key">AWS Secret Key</Label>
                  <Input
                    id="aws_access_key"
                    type="password"
                    value={settings.aws_access_key}
                    onChange={(e) => handleInputChange('aws_access_key', e.target.value)}
                    placeholder="Enter AWS Secret Access Key"
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="bucket_name">S3 Bucket Name</Label>
                  <Input
                    id="bucket_name"
                    value={settings.bucket_name}
                    onChange={(e) => handleInputChange('bucket_name', e.target.value)}
                    placeholder="your-bucket-name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="region">AWS Region</Label>
                  <Input
                    id="region"
                    value={settings.region}
                    onChange={(e) => handleInputChange('region', e.target.value)}
                    placeholder="us-east-1"
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* TWS Management Settings (Disabled) */}
        <Card className="opacity-60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              TWS Management (Coming Soon)
            </CardTitle>
            <CardDescription>
              Automatic TWS startup and authentication (not yet implemented)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center space-x-2">
              <Switch
                id="auto_start_tws"
                checked={settings.auto_start_tws === 'True'}
                onCheckedChange={(checked) => handleSwitchChange('auto_start_tws', checked)}
                disabled
              />
              <Label htmlFor="auto_start_tws" className="text-muted-foreground">
                Auto-start TWS
              </Label>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="username" className="text-muted-foreground">Username</Label>
                <Input
                  id="username"
                  value={settings.username}
                  onChange={(e) => handleInputChange('username', e.target.value)}
                  placeholder="IB Username"
                  disabled
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-muted-foreground">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={settings.password}
                  onChange={(e) => handleInputChange('password', e.target.value)}
                  placeholder="IB Password"
                  disabled
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Save Button at Bottom */}
      <div className="flex justify-end pt-6 border-t">
        <Button
          onClick={saveSettings}
          disabled={saving}
          size="lg"
        >
          <Save className={`h-4 w-4 mr-2 ${saving ? 'animate-spin' : ''}`} />
          Save Settings
        </Button>
      </div>
    </div>
  );
};

export default Settings;
