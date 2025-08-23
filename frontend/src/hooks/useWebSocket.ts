import { useState, useEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  timestamp: string;
  level: string;
  component: string;
  message: string;
}

export interface ConnectionStatus {
  connected: boolean;
  error: string | null;
  host: string | null;
  port: number | null;
  client_id: number | null;
  message: string | null;
}

// Global state for shared WebSocket connection
let globalWs: WebSocket | null = null;
let globalLogs: LogEntry[] = [];
let globalConnectionStatus: ConnectionStatus = {
  connected: false,
  error: null,
  host: null,
  port: null,
  client_id: null,
  message: null
};

// Subscribers for state updates
const logSubscribers = new Set<(logs: LogEntry[]) => void>();
const connectionSubscribers = new Set<(status: ConnectionStatus) => void>();
const wsStatusSubscribers = new Set<(connected: boolean) => void>();

let reconnectTimer: NodeJS.Timeout | null = null;

const connectWebSocket = () => {
  // Prevent multiple connections
  if (globalWs && globalWs.readyState === WebSocket.OPEN) {
    return;
  }

  console.log('Creating shared WebSocket connection...');
  globalWs = new WebSocket('ws://127.0.0.1:8000/ws');

  globalWs.onopen = () => {
    console.log('Shared WebSocket connected');
    wsStatusSubscribers.forEach(callback => callback(true));
  };

  globalWs.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.type === 'log') {
        const newLog: LogEntry = {
          timestamp: data.timestamp,
          level: data.level,
          component: data.component,
          message: data.message
        };
        
        globalLogs = [...globalLogs, newLog];
        logSubscribers.forEach(callback => callback([...globalLogs]));
        
      } else if (data.type === 'connection_status') {
        globalConnectionStatus = {
          connected: data.connected,
          host: data.host,
          port: data.port,
          client_id: data.client_id,
          error: data.error,
          message: data.message
        };
        connectionSubscribers.forEach(callback => callback({...globalConnectionStatus}));
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  };

  globalWs.onclose = () => {
    console.log('Shared WebSocket disconnected');
    wsStatusSubscribers.forEach(callback => callback(false));
    
    // Attempt to reconnect after 3 seconds
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectWebSocket, 3000);
  };

  globalWs.onerror = (error) => {
    console.error('Shared WebSocket error:', error);
    wsStatusSubscribers.forEach(callback => callback(false));
  };
};

export const useWebSocket = () => {
  const [logs, setLogs] = useState<LogEntry[]>(globalLogs);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(globalConnectionStatus);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    // Subscribe to updates
    logSubscribers.add(setLogs);
    connectionSubscribers.add(setConnectionStatus);
    wsStatusSubscribers.add(setWsConnected);

    // Initialize connection if not exists
    if (!globalWs || globalWs.readyState === WebSocket.CLOSED) {
      connectWebSocket();
    } else if (globalWs.readyState === WebSocket.OPEN) {
      setWsConnected(true);
    }

    // Set initial state
    setLogs([...globalLogs]);
    setConnectionStatus({...globalConnectionStatus});

    return () => {
      // Unsubscribe
      logSubscribers.delete(setLogs);
      connectionSubscribers.delete(setConnectionStatus);
      wsStatusSubscribers.delete(setWsConnected);
    };
  }, []);

  const clearLogs = useCallback(() => {
    globalLogs = [];
    logSubscribers.forEach(callback => callback([]));
  }, []);

  return {
    logs,
    connectionStatus,
    wsConnected,
    clearLogs
  };
};
