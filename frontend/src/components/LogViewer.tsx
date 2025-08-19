import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  Terminal, 
  Trash2, 
  Download,
  Pause,
  Play,
  Circle
} from 'lucide-react';

interface LogEntry {
  timestamp: string;
  level: string;
  component: string;
  message: string;
}

interface ConnectionStatus {
  connected: boolean;
  host?: string;
  port?: number;
  client_id?: number;
  error?: string;
  message?: string;
}

const LogViewer = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({ connected: false });
  const [isPaused, setIsPaused] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Auto-scroll to bottom when new logs arrive
  const scrollToBottom = () => {
    if (scrollAreaRef.current && !isPaused) {
      const scrollContainer = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [logs, isPaused]);

  // WebSocket connection
  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;

    const connectWebSocket = () => {
      // Prevent multiple connections
      if (ws && ws.readyState === WebSocket.OPEN) {
        return;
      }

      ws = new WebSocket('ws://127.0.0.1:8000/ws');
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('LogViewer WebSocket connected');
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'log') {
            const newLog: LogEntry = {
              timestamp: data.timestamp,
              level: data.level,
              component: data.component,
              message: data.message
            };
            
            if (!isPaused) {
              setLogs(prev => [...prev, newLog]);
            }
          } else if (data.type === 'connection_status') {
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
        console.log('LogViewer WebSocket disconnected');
        setWsConnected(false);
        // Attempt to reconnect after 3 seconds
        reconnectTimer = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (error) => {
        console.error('LogViewer WebSocket error:', error);
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
  }, [isPaused]);

  const clearLogs = () => {
    setLogs([]);
  };

  const downloadLogs = () => {
    const logText = logs.map(log => 
      `[${log.timestamp}] ${log.level} ${log.component}: ${log.message}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ib-ats-logs-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const togglePause = () => {
    setIsPaused(!isPaused);
  };

  const getLevelColor = (level: string) => {
    switch (level.toLowerCase()) {
      case 'error': return 'text-red-500';
      case 'warning': return 'text-yellow-500';
      case 'info': return 'text-blue-500';
      case 'debug': return 'text-gray-500';
      default: return 'text-foreground';
    }
  };

  const getConnectionBadge = () => {
    if (!wsConnected) {
      return <Badge variant="destructive">WebSocket Disconnected</Badge>;
    }
    
    if (connectionStatus.connected) {
      return (
        <Badge variant="default" className="bg-green-600">
          IB Connected ({connectionStatus.host}:{connectionStatus.port})
        </Badge>
      );
    } else {
      return (
        <Badge variant="destructive">
          IB Offline {connectionStatus.error ? `- ${connectionStatus.error}` : ''}
        </Badge>
      );
    }
  };

  return (
    <Card className="h-[600px] flex flex-col">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5" />
            <CardTitle>System Logs</CardTitle>
            <div className="flex items-center gap-1">
              <Circle className={`h-2 w-2 ${wsConnected ? 'fill-green-500 text-green-500' : 'fill-red-500 text-red-500'}`} />
              <span className="text-xs text-muted-foreground">
                {wsConnected ? 'Live' : 'Disconnected'}
              </span>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            {getConnectionBadge()}
            
            <Button
              variant="outline"
              size="sm"
              onClick={togglePause}
              className="h-8 w-8 p-0"
            >
              {isPaused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
            </Button>
            
            <Button
              variant="outline"
              size="sm"
              onClick={downloadLogs}
              className="h-8 w-8 p-0"
            >
              <Download className="h-3 w-3" />
            </Button>
            
            <Button
              variant="outline"
              size="sm"
              onClick={clearLogs}
              className="h-8 w-8 p-0"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="flex-1 p-0 overflow-hidden">
        <div className="h-full bg-black/5 dark:bg-white/5 rounded-md border">
          <ScrollArea className="h-full" ref={scrollAreaRef}>
            <div className="p-4 space-y-1 font-mono text-sm">
              {logs.length === 0 ? (
                <div className="text-muted-foreground text-center py-8">
                  {wsConnected ? 'Waiting for log messages...' : 'Connecting to backend...'}
                </div>
              ) : (
                logs.map((log, index) => (
                  <div key={index} className="flex gap-2 py-1 hover:bg-muted/50 rounded px-2 min-h-[24px]">
                    <span className="text-muted-foreground text-xs shrink-0 w-20">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                    <Badge 
                      variant="outline" 
                      className={`text-xs shrink-0 w-20 justify-center ${getLevelColor(log.level)}`}
                    >
                      {log.component}
                    </Badge>
                    <span className="text-sm break-words flex-1">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
};

export default LogViewer;
