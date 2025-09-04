import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useWebSocket } from '@/hooks/useWebSocket';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { 
  Activity, 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  BarChart3,
  Settings as SettingsIcon,
  Play,
  Pause,
  Square,
  Plus,
  Terminal,
  Circle,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import StrategyManager from './StrategyManager';
import PortfolioView from './PortfolioView';
import TradeExecution from './TradeExecution';
import PerformanceAnalytics from './PerformanceAnalytics';
import LogViewer from './LogViewer';
import ArcticDBView from './ArcticDBView';
import SettingsComponent from './Settings';

const TradingDashboard = () => {
  const [activeStrategies, setActiveStrategies] = useState(0);
  const [totalPnL, setTotalPnL] = useState(12547.89);
  const [todayPnL, setTodayPnL] = useState(284.56);
  const [portfolioValue, setPortfolioValue] = useState(250000);
  const [totalStrategies, setTotalStrategies] = useState(0);
  const { connectionStatus, wsConnected } = useWebSocket();

  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);
  const [showConnectionDialog, setShowConnectionDialog] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [connectionDetails, setConnectionDetails] = useState(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [ibConnectionStatus, setIbConnectionStatus] = useState({ 
    connected: false, 
    loading: true, 
    host: null as string | null, 
    port: null as number | null 
  });
  const [showTopLogs, setShowTopLogs] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('strategies');
  const [showFullLogs, setShowFullLogs] = useState(false);

  // Fetch IB connection status on component mount
  useEffect(() => {
    checkIbConnectionStatus();
    fetchStrategyCounts();
  }, []);

  const checkIbConnectionStatus = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/ib-status');
      const data = await response.json();
      if (data.success) {
        setIbConnectionStatus({ 
          connected: data.connection_status.master_connection.connected,
          loading: false,
          host: data.connection_status.master_connection.host,
          port: data.connection_status.master_connection.port
        });
      } else {
        setIbConnectionStatus({ connected: false, loading: false, host: null, port: null });
      }
    } catch (error) {
      console.error('Failed to check IB connection status:', error);
      setIbConnectionStatus({ connected: false, loading: false, host: null, port: null });
    }
  };

  const fetchStrategyCounts = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/strategies');
      const data = await response.json();
      const list = Array.isArray(data?.strategies) ? data.strategies : [];
      setTotalStrategies(list.length);
      const active = list.filter((s: any) => !!s.active).length;
      setActiveStrategies(active);
    } catch (error) {
      console.error('Failed to fetch strategy counts:', error);
    }
  };

  const handleConnectionToggle = async () => {
    if (ibConnectionStatus.connected) {
      await fetchConnectionDetails();
      setShowConnectionDialog(true);
    } else {
      // If offline, attempt manual connection
      await handleManualConnect();
    }
  };

  const handleManualConnect = async () => {
    setIbConnectionStatus(prev => ({ ...prev, loading: true }));
    
    try {
      const response = await fetch('http://127.0.0.1:8000/api/ib-connect', {
        method: 'POST',
      });
      const data = await response.json();
      
      if (data.success) {
        // Refresh connection status after successful connection
        await checkIbConnectionStatus();
      } else {
        console.error('Failed to connect to IB:', data.message);
        setIbConnectionStatus(prev => ({ ...prev, loading: false }));
      }
    } catch (error) {
      console.error('Error connecting to IB:', error);
      setIbConnectionStatus(prev => ({ ...prev, loading: false }));
    }
  };

  const fetchConnectionDetails = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/ib-status');
      const data = await response.json();
      if (data.success) {
        setConnectionDetails(data.connection_status);
      }
    } catch (error) {
      console.error('Failed to fetch connection details:', error);
    }
  };

  const handleDisconnectClient = async (clientId) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/ib-disconnect-client/${clientId}`, { method: 'POST' });
      await fetchConnectionDetails(); // Refresh connection details
      await checkIbConnectionStatus(); // Refresh main connection status
    } catch (error) {
      console.error('Disconnect client failed:', error);
    }
  };

  const handleDisconnectAll = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/ib-disconnect-all', { method: 'POST' });
      setShowConnectionDialog(false);
      setShowDisconnectDialog(false);
      // Refresh connection status after disconnect
      await checkIbConnectionStatus();
    } catch (error) {
      console.error('Disconnect all failed:', error);
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">IB Multi-Strategy ATS</h1>
            <p className="text-muted-foreground">Automated Trading System Dashboard</p>
          </div>
          <div className="flex items-center gap-4">
            <Button 
              variant="outline" 
              size="sm"
              onClick={handleConnectionToggle}
              disabled={ibConnectionStatus.loading}
              className={ibConnectionStatus.connected ? 'border-green-500 text-green-600' : 'border-red-500 text-red-600'}
            >
              <Circle className={`h-3 w-3 mr-2 ${ibConnectionStatus.connected ? 'fill-green-500' : 'fill-red-500'}`} />
              {ibConnectionStatus.loading ? 'Connecting...' : ibConnectionStatus.connected ? `IB Connected (${ibConnectionStatus.host}:${ibConnectionStatus.port})` : 'Connect to IB'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowSettingsDialog(true)}>
              <SettingsIcon className="h-4 w-4 mr-2" />
              Settings
            </Button>
          </div>
        </div>

        {/* Slider: Metrics <-> Logs (no extra container chrome) */}
        <div
          className="relative overflow-hidden transition-[height] duration-300 ease-in-out"
          style={{ height: showTopLogs ? 220 : 'auto' }}
        >
          {/* Metrics Panel (in normal flow) */}
          <div className={`transition-opacity duration-300 ${showTopLogs ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Portfolio Value</CardTitle>
                  <DollarSign className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">${portfolioValue.toLocaleString()}</div>
                  <p className="text-xs text-muted-foreground">Total account value</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total P&L</CardTitle>
                  <TrendingUp className="h-4 w-4 text-profit" />
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${totalPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
                    ${totalPnL.toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground">All-time performance</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Today's P&L</CardTitle>
                  {todayPnL >= 0 ? (
                    <TrendingUp className="h-4 w-4 text-profit" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-loss" />
                  )}
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${todayPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
                    ${todayPnL.toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground">Today's performance</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Strategies</CardTitle>
                  <Activity className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{totalStrategies}</div>
                  <p className="text-xs text-muted-foreground">Active: {activeStrategies}</p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Logs Panel (absolute overlay) */}
          <div className={`absolute inset-0 transition-transform duration-300 ${showTopLogs ? 'translate-x-0' : 'translate-x-full'}`}>
            <LogViewer
              compact
              height={220}
              onMaximize={() => {
                setShowTopLogs(false);
                setShowFullLogs(true);
              }}
            />
          </div>

          {/* Slider Handle */}
          <button
            type="button"
            onClick={() => setShowTopLogs(v => !v)}
            className="absolute top-1/2 -translate-y-1/2 right-2 z-10 p-0 m-0 bg-transparent text-muted-foreground/60 hover:text-muted-foreground transition-colors"
            aria-label="Toggle dashboard views"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        </div>

        {/* Main Content Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="strategies">Strategies</TabsTrigger>
            <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
            <TabsTrigger value="execution">Execution</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
            <TabsTrigger value="data">ArcticDB</TabsTrigger>
          </TabsList>

          <TabsContent value="strategies" className="space-y-4">
            <StrategyManager />
          </TabsContent>

          <TabsContent value="portfolio" className="space-y-4">
            <PortfolioView />
          </TabsContent>

          <TabsContent value="execution" className="space-y-4">
            <TradeExecution />
          </TabsContent>

          <TabsContent value="analytics" className="space-y-4">
            <PerformanceAnalytics />
          </TabsContent>

          <TabsContent value="data" className="space-y-4">
            <ArcticDBView />
          </TabsContent>
        </Tabs>

        {/* Full-Screen Logs Overlay */}
        {showFullLogs && (
          <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm">
            <div className="absolute top-4 right-4 flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowFullLogs(false)}>Close</Button>
            </div>
            <div className="h-full p-6">
              <LogViewer />
            </div>
          </div>
        )}

        {/* Connection Management Dialog */}
        <Dialog open={showConnectionDialog} onOpenChange={setShowConnectionDialog}>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>IB Connection Management</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              {connectionDetails && (
                <>
                  {/* Master Connection */}
                  <div className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Circle className={`h-3 w-3 ${connectionDetails.master_connection.connected ? 'fill-green-500' : 'fill-red-500'}`} />
                        <span className="font-medium">Master Connection</span>
                        <Badge variant="outline">Client ID: {connectionDetails.master_connection.client_id}</Badge>
                      </div>
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => handleDisconnectClient(connectionDetails.master_connection.client_id)}
                        disabled={!connectionDetails.master_connection.connected}
                      >
                        Disconnect
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {connectionDetails.master_connection.host}:{connectionDetails.master_connection.port}
                    </p>
                  </div>

                  {/* Strategy Connections */}
                  {connectionDetails.strategy_connections.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="font-medium">Strategy Connections</h4>
                      {connectionDetails.strategy_connections.map((strategy) => (
                        <div key={strategy.client_id} className="border rounded-lg p-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <Circle className={`h-3 w-3 ${strategy.connected ? 'fill-green-500' : 'fill-red-500'}`} />
                              <span className="font-medium">{strategy.strategy_name}</span>
                              <Badge variant="outline">Client ID: {strategy.client_id}</Badge>
                              <Badge variant="secondary">{strategy.symbol}</Badge>
                            </div>
                            <Button 
                              variant="outline" 
                              size="sm"
                              onClick={() => handleDisconnectClient(strategy.client_id)}
                              disabled={!strategy.connected}
                            >
                              Disconnect
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Disconnect All Button */}
                  <div className="pt-4 border-t">
                    <Button 
                      variant="destructive" 
                      onClick={() => setShowDisconnectDialog(true)}
                      className="w-full"
                    >
                      Disconnect All Connections
                    </Button>
                  </div>
                </>
              )}
            </div>
          </DialogContent>
        </Dialog>

        {/* Disconnect All Confirmation Dialog */}
        <AlertDialog open={showDisconnectDialog} onOpenChange={setShowDisconnectDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Disconnect All IB Connections?</AlertDialogTitle>
              <AlertDialogDescription>
                This will disconnect all IB connections (master + all strategies). 
                All active strategies will be stopped and you won't receive market data.
                Are you sure you want to continue?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDisconnectAll} className="bg-red-600 hover:bg-red-700">
                Yes, Disconnect All
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Settings Dialog */}
        <Dialog open={showSettingsDialog} onOpenChange={setShowSettingsDialog}>
          <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>System Settings</DialogTitle>
            </DialogHeader>
            <SettingsComponent />
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
};

export default TradingDashboard;