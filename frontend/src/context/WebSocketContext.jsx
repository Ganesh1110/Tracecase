import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';

const WebSocketContext = createContext({
  connected: false,
  lastEvent: null,
  sendMessage: () => {},
  subscribe: () => {},
});

export function WebSocketProvider({ children }) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const socketRef = useRef(null);
  const listenersRef = useRef(new Map());

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/ws`;

    let socket;
    let reconnectTimer;

    const connect = () => {
      socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastEvent(data);
          // Trigger any channel-specific listeners
          if (data.channel && listenersRef.current.has(data.channel)) {
            listenersRef.current.get(data.channel).forEach((cb) => cb(data));
          }
          if (data.type && listenersRef.current.has(data.type)) {
            listenersRef.current.get(data.type).forEach((cb) => cb(data));
          }
        } catch {
          // ignore non-json
        }
      };

      socket.onclose = () => {
        setConnected(false);
        // Attempt reconnect after 3 seconds
        reconnectTimer = setTimeout(connect, 3000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  const sendMessage = useCallback((msg) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  }, []);

  const subscribe = useCallback((channelOrType, callback) => {
    if (!listenersRef.current.has(channelOrType)) {
      listenersRef.current.set(channelOrType, new Set());
    }
    listenersRef.current.get(channelOrType).add(callback);

    // If it's a channel name, announce subscription to backend
    if (channelOrType.startsWith('execution:') || channelOrType.startsWith('recording:')) {
      sendMessage({ action: 'subscribe', channel: channelOrType });
    }

    return () => {
      if (listenersRef.current.has(channelOrType)) {
        listenersRef.current.get(channelOrType).delete(callback);
      }
    };
  }, [sendMessage]);

  return (
    <WebSocketContext.Provider value={{ connected, lastEvent, sendMessage, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export const useWebSocket = () => useContext(WebSocketContext);
