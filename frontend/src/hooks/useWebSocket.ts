/**
 * WebSocket Hook for Real-time Communication with FastAPI Backend
 * Handles connection management, message routing, and state synchronization
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export type MessageType = 
  | 'start_recording'
  | 'stop_recording' 
  | 'pause_recording'
  | 'transcribe_buffer'
  | 'transcribe_last_30'
  | 'get_audio_buffer'
  | 'load_test_audio'
  | 'analyze_transcript'
  | 'recording_status'
  | 'transcription_result'
  | 'analysis_result'
  | 'audio_buffer_result'
  | 'stream_chunk'
  | 'status_update'
  | 'error';

export interface WebSocketMessage {
  type: MessageType;
  data: any;
}

export interface ConnectionStatus {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  lastConnected: Date | null;
}

export interface RecordingStatus {
  is_recording: boolean;
  is_paused: boolean;
  buffer_duration: number;
  buffer_max_duration: number;
}

export interface TranscriptionResult {
  transcript: string;
  duration_type: 'full_buffer' | 'last_30_seconds';
  timestamp: number;
}

export interface AnalysisResult {
  result: string;
  analysis_type: string;
  timestamp: number;
}

export interface StreamChunk {
  chunk: string;
  analysis_type: string;
  prompt_id: string;
}

export interface StatusUpdate {
  message: string;
}

export interface ErrorMessage {
  message: string;
}

export const useWebSocket = (url: string = 'ws://127.0.0.1:8000/ws') => {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 3000;

  // Connection state
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    isConnected: false,
    isConnecting: false,
    error: null,
    lastConnected: null
  });

  // Application state from WebSocket messages
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatus>({
    is_recording: false,
    is_paused: false,
    buffer_duration: 0,
    buffer_max_duration: 180
  });

  // Message handlers
  const messageHandlers = useRef<{
    [K in MessageType]?: (data: any) => void;
  }>({});

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Close existing connection if any
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }

    setConnectionStatus(prev => ({ 
      ...prev, 
      isConnecting: true, 
      error: null 
    }));

    // Add a small delay to ensure backend is ready
    setTimeout(() => {
      try {
        ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        console.log('🔌 WebSocket connected');
        setConnectionStatus({
          isConnected: true,
          isConnecting: false,
          error: null,
          lastConnected: new Date()
        });
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleMessage(message);
        } catch (error) {
          console.error('❌ Failed to parse WebSocket message:', error);
        }
      };

      ws.current.onclose = (event) => {
        console.log('🔌 WebSocket disconnected:', event.code, event.reason);
        setConnectionStatus(prev => ({
          ...prev,
          isConnected: false,
          isConnecting: false
        }));

        // Attempt reconnection if not a normal closure
        if (event.code !== 1000 && reconnectAttempts.current < maxReconnectAttempts) {
          scheduleReconnect();
        }
      };

        ws.current.onerror = (error) => {
          console.error('❌ WebSocket error:', error);
          setConnectionStatus(prev => ({
            ...prev,
            isConnected: false,
            isConnecting: false,
            error: 'Connection failed'
          }));
        };

      } catch (error) {
        console.error('❌ Failed to create WebSocket connection:', error);
        setConnectionStatus(prev => ({
          ...prev,
          isConnecting: false,
          error: 'Failed to connect'
        }));
      }
    }, 100); // 100ms delay to ensure backend is ready
  }, [url]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    reconnectAttempts.current++;
    const delay = reconnectDelay * Math.pow(2, reconnectAttempts.current - 1);

    console.log(`🔄 Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`);

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (ws.current) {
      ws.current.close(1000, 'Normal closure');
      ws.current = null;
    }

    setConnectionStatus(prev => ({
      ...prev,
      isConnected: false,
      isConnecting: false
    }));
  }, []);

  const sendMessage = useCallback((type: MessageType, data: any = {}) => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      console.error('❌ WebSocket not connected');
      return false;
    }

    try {
      const message: WebSocketMessage = { type, data };
      ws.current.send(JSON.stringify(message));
      console.log('📤 Sent:', type, data);
      return true;
    } catch (error) {
      console.error('❌ Failed to send message:', error);
      return false;
    }
  }, []);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    console.log('📥 Received:', message.type, message.data);

    // Handle built-in message types
    switch (message.type) {
      case 'recording_status':
        setRecordingStatus(message.data);
        break;
    }

    // Call registered handler if exists
    const handler = messageHandlers.current[message.type];
    if (handler) {
      handler(message.data);
    }
  }, []);

  const onMessage = useCallback(<T extends MessageType>(
    type: T,
    handler: (data: any) => void
  ) => {
    messageHandlers.current[type] = handler;

    // Return cleanup function
    return () => {
      delete messageHandlers.current[type];
    };
  }, []);

  // Audio control methods
  const startRecording = useCallback(() => {
    return sendMessage('start_recording');
  }, [sendMessage]);

  const stopRecording = useCallback(() => {
    return sendMessage('stop_recording');
  }, [sendMessage]);

  const pauseRecording = useCallback(() => {
    return sendMessage('pause_recording');
  }, [sendMessage]);

  const transcribeBuffer = useCallback(() => {
    return sendMessage('transcribe_buffer');
  }, [sendMessage]);

  const transcribeLast30 = useCallback(() => {
    return sendMessage('transcribe_last_30');
  }, [sendMessage]);

  const analyzeTranscript = useCallback((transcript: string, promptId: string, analysisType?: string) => {
    return sendMessage('analyze_transcript', {
      transcript,
      prompt_id: promptId,
      analysis_type: analysisType || promptId
    });
  }, [sendMessage]);

  const getAudioBuffer = useCallback(() => {
    return sendMessage('get_audio_buffer');
  }, [sendMessage]);

  const loadTestAudio = useCallback(() => {
    return sendMessage('load_test_audio');
  }, [sendMessage]);

  // Initialize connection on mount with retry logic
  useEffect(() => {
    // Initial connection attempt
    const initialConnect = () => {
      connect();
    };

    // Small delay on mount to handle page refresh scenarios
    const mountTimer = setTimeout(initialConnect, 200);

    // Cleanup function
    return () => {
      clearTimeout(mountTimer);
      disconnect();
    };
  }, [connect, disconnect]);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    // Connection state
    connectionStatus,
    recordingStatus,
    
    // Connection methods
    connect,
    disconnect,
    
    // Messaging
    sendMessage,
    onMessage,
    
    // Audio controls
    startRecording,
    stopRecording,
    pauseRecording,
    transcribeBuffer,
    transcribeLast30,
    analyzeTranscript,
    getAudioBuffer,
    loadTestAudio
  };
};

export default useWebSocket;