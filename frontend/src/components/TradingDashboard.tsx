import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  Activity, 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  BarChart3,
  Settings,
  Play,
  Pause,
  Square,
  Plus,
  Terminal,
  Circle
} from 'lucide-react';
import StrategyManager from './StrategyManager';
import PortfolioView from './PortfolioView';
import TradeExecution from './TradeExecution';
import PerformanceAnalytics from './PerformanceAnalytics';
import LogViewer from './LogViewer';

const TradingDashboard = () => {
  const [activeStrategies, setActiveStrategies] = useState(3);
  const [totalPnL, setTotalPnL] = useState(12547.89);
  const [todayPnL, setTodayPnL] = useState(284.56);
  const [portfolioValue, setPortfolioValue] = useState(250000);
  const [connectionStatus, setConnectionStatus] = useState({ 
    connected: false, 
    error: null, 
    host: null, 
    port: null, 
    client_id: null, 
    message: null 
  });
  const [wsConnected, setWsConnected] = useState(false);

  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  // WebSocket connection for real-time status updates
  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;

    const connectWebSocket = () => {
      // Prevent multiple connections
      if (ws && ws.readyState === WebSocket.OPEN) {
        return;
      }

      ws = new WebSocket('ws://127.0.0.1:8000/ws');

      ws.onopen = () => {
        setWsConnected(true);
        console.log('Dashboard WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'connection_status') {
            setConnectionStatus({
              connected: data.connected,
              host: data.host,
              port: data.port,
              client_id: data.client_id,
              error: data.error,
              message: data.message
            });
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        console.log('Dashboard WebSocket disconnected');
        // Attempt to reconnect after 3 seconds
        reconnectTimer = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (error) => {
        console.error('Dashboard WebSocket error:', error);
        setWsConnected(false);
      };
    };

    connectWebSocket();

    return () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (ws) {
        ws.close();
      }
    };
  }, []);

  const handleConnectionToggle = async () => {
    if (connectionStatus.connected) {
      setShowDisconnectDialog(true);
    } else {
      await handleConnect();
    }
  };

  const handleConnect = async () => {
    if (isConnecting) return; // Prevent multiple simultaneous connections
    
    setIsConnecting(true);
    try {
      await fetch('http://127.0.0.1:8000/api/ib-test');
    } catch (error) {
      console.error('Connection failed:', error);
    } finally {
      setIsConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/ib-disconnect', { method: 'POST' });
      setShowDisconnectDialog(false);
    } catch (error) {
      console.error('Disconnect failed:', error);
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
              disabled={isConnecting}
              className={connectionStatus.connected ? 'border-green-500 text-green-600' : 'border-red-500 text-red-600'}
            >
              <Circle className={`h-3 w-3 mr-2 ${connectionStatus.connected ? 'fill-green-500' : 'fill-red-500'}`} />
              {isConnecting ? 'Connecting...' : connectionStatus.connected ? `IB Connected (${connectionStatus.host}:${connectionStatus.port})` : 'IB Offline'}
            </Button>
            <Button variant="outline" size="sm">
              <Settings className="h-4 w-4 mr-2" />
              Settings
            </Button>
          </div>
        </div>

        {/* Key Metrics */}
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
              {todayPnL >= 0 ? 
                <TrendingUp className="h-4 w-4 text-profit" /> : 
                <TrendingDown className="h-4 w-4 text-loss" />
              }
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
              <CardTitle className="text-sm font-medium">Active Strategies</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{activeStrategies}</div>
              <p className="text-xs text-muted-foreground">Currently running</p>
            </CardContent>
          </Card>
        </div>

        {/* Main Content Tabs */}
        <Tabs defaultValue="strategies" className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="strategies">Strategies</TabsTrigger>
            <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
            <TabsTrigger value="execution">Execution</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
            <TabsTrigger value="logs">
              <Terminal className="h-4 w-4 mr-2" />
              Logs
            </TabsTrigger>
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

          <TabsContent value="logs" className="space-y-4">
            <LogViewer />
          </TabsContent>
        </Tabs>

        {/* Disconnect Confirmation Dialog */}
        <AlertDialog open={showDisconnectDialog} onOpenChange={setShowDisconnectDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Disconnect from Interactive Brokers?</AlertDialogTitle>
              <AlertDialogDescription>
                This will disconnect your trading system from Interactive Brokers. 
                All active strategies will be stopped and you won't receive market data.
                Are you sure you want to continue?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDisconnect} className="bg-red-600 hover:bg-red-700">
                Yes, Disconnect
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
};

export default TradingDashboard;