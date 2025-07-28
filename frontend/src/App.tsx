import React, { useState, useRef, useEffect } from 'react';
import { 
  Mic, 
  MicOff,
  Play,
  Pause,
  Square,
  FileText,
  Brain,
  Clock,
  Users,
  MessageSquare,
  Zap,
  CheckCircle,
  AlertCircle,
  Download,
  Settings,
  Volume2,
  VolumeX,
  Wifi,
  WifiOff,
  RefreshCw,
  PlayCircle,
  Upload
} from 'lucide-react';

import useWebSocket from './hooks/useWebSocket';
import { apiClient, type PromptInfo } from './api/client';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: number;
  speaker?: string;
  duration_type?: 'full_buffer' | 'last_30_seconds';
}

interface AnalysisResult {
  type: string;
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

const AudioVisualizer = ({ isRecording, audioLevel = 0 }: { isRecording: boolean; audioLevel: number }) => {
  return (
    <div className="flex items-center justify-center space-x-1 h-12">
      {[...Array(20)].map((_, i) => (
        <div
          key={i}
          className={`w-1 bg-gradient-to-t from-teal-500 to-blue-500 rounded-full transition-all duration-150 ${
            isRecording ? 'animate-pulse' : ''
          }`}
          style={{
            height: isRecording 
              ? `${Math.random() * 40 + 8}px` 
              : '8px',
            opacity: isRecording ? Math.random() * 0.8 + 0.2 : 0.3
          }}
        />
      ))}
    </div>
  );
};

const StatusIndicator = ({ 
  status, 
  message, 
  isConnected 
}: { 
  status: 'idle' | 'recording' | 'processing' | 'error'; 
  message: string;
  isConnected: boolean;
}) => {
  const getStatusColor = () => {
    if (!isConnected) return 'text-red-400';
    switch (status) {
      case 'recording': return 'text-red-400';
      case 'processing': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      default: return 'text-slate-400';
    }
  };

  const getStatusIcon = () => {
    if (!isConnected) return <WifiOff className="w-4 h-4 text-red-400" />;
    switch (status) {
      case 'recording': return <div className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />;
      case 'processing': return <div className="w-2 h-2 bg-yellow-400 rounded-full animate-spin" />;
      case 'error': return <AlertCircle className="w-4 h-4 text-red-400" />;
      default: return <Wifi className="w-4 h-4 text-green-400" />;
    }
  };

  const displayMessage = !isConnected ? 'Disconnected' : message;

  return (
    <div className="flex items-center space-x-2">
      {getStatusIcon()}
      <span className={`text-sm ${getStatusColor()}`}>{displayMessage}</span>
    </div>
  );
};

const TranscriptionPanel = ({ segments }: { segments: TranscriptionSegment[] }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [segments]);

  return (
    <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 h-96">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
          <FileText className="w-5 h-5" />
          <span>Live Transcription</span>
        </h3>
        <button className="p-2 hover:bg-white/10 rounded-lg transition-colors duration-200">
          <Download className="w-4 h-4 text-slate-400" />
        </button>
      </div>
      
      <div 
        ref={scrollRef}
        className="h-80 overflow-y-auto space-y-3 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent"
      >
        {segments.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500">
            <div className="text-center">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Transcription will appear here...</p>
            </div>
          </div>
        ) : (
          segments.map((segment) => (
            <div key={segment.id} className="group">
              <div className="flex items-start space-x-3">
                <div className="text-xs text-slate-500 mt-1 min-w-[60px]">
                  {new Date(segment.timestamp).toLocaleTimeString([], { 
                    hour: '2-digit', 
                    minute: '2-digit',
                    second: '2-digit'
                  })}
                </div>
                <div className="flex-1">
                  {segment.speaker && (
                    <div className="text-xs text-teal-400 mb-1 font-medium">
                      {segment.speaker}
                    </div>
                  )}
                  <p className="text-slate-200 leading-relaxed group-hover:text-white transition-colors duration-200">
                    {segment.text}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const AnalysisPanel = ({ 
  analyses, 
  onAnalyze, 
  prompts, 
  isLoading 
}: { 
  analyses: AnalysisResult[]; 
  onAnalyze: (promptId: string, promptLabel: string) => void;
  prompts: PromptInfo[];
  isLoading: boolean;
}) => {
  const getIconForPrompt = (promptId: string) => {
    const iconMap: Record<string, any> = {
      'meeting_summary': Users,
      'follow_up_questions': MessageSquare,
      'topic_summary': Brain,
      'sentiment_analysis': Zap,
      'fact_check': CheckCircle,
      'gaps_reasoning': AlertCircle,
      'brainstorming': MessageSquare,
      'scqa': Brain,
      'hypothesis_driven': Brain,
      'first_principles': Brain,
      'company_fit': CheckCircle,
      'answer_question': MessageSquare,
      'practitioner_insights': Brain,
      'issue_tree': Brain,
      'reframing': Brain
    };
    return iconMap[promptId] || Brain;
  };

  return (
    <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 h-96">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
          <Brain className="w-5 h-5" />
          <span>AI Analysis</span>
        </h3>
      </div>
      
      <div className="grid grid-cols-2 gap-2 mb-6 max-h-48 overflow-y-auto">
        {isLoading ? (
          <div className="col-span-2 flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-teal-400"></div>
            <span className="ml-2 text-slate-400">Loading prompts...</span>
          </div>
        ) : prompts.length === 0 ? (
          <div className="col-span-2 text-center py-8 text-slate-500">
            No prompts available
          </div>
        ) : (
          prompts.map((prompt) => {
            const Icon = getIconForPrompt(prompt.id);
            return (
              <button
                key={prompt.id}
                onClick={() => onAnalyze(prompt.id, prompt.button_text)}
                className="p-2 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-white/5 hover:border-white/10 transition-all duration-200 group"
                title={prompt.output_title}
              >
                <div className="flex items-center space-x-2">
                  <Icon className="w-3 h-3 text-slate-400 group-hover:text-teal-400 transition-colors duration-200 flex-shrink-0" />
                  <span className="text-xs text-slate-300 group-hover:text-white transition-colors duration-200 truncate">
                    {prompt.button_text}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
      
      <div className="h-48 overflow-y-auto space-y-3 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent">
        {analyses.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500">
            <div className="text-center">
              <Brain className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Select an analysis type to begin</p>
            </div>
          </div>
        ) : (
          analyses.map((analysis, index) => (
            <div key={index} className={`bg-slate-700/30 rounded-xl p-4 border ${
              analysis.isStreaming ? 'border-teal-400/30 bg-teal-900/10' : 'border-white/5'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <span className="text-sm font-medium text-teal-400 capitalize">
                    {analysis.type}
                  </span>
                  {analysis.isStreaming && (
                    <div className="flex items-center space-x-1">
                      <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse"></div>
                      <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse delay-75"></div>
                      <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse delay-150"></div>
                    </div>
                  )}
                </div>
                <span className="text-xs text-slate-500">
                  {new Date(analysis.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-slate-200 text-sm leading-relaxed">
                {analysis.content}
                {analysis.isStreaming && (
                  <span className="inline-block w-2 h-4 bg-teal-400 ml-1 animate-pulse"></span>
                )}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

function App() {
  // Icon mapping for prompts
  const getIconForPrompt = (promptId: string) => {
    const iconMap: Record<string, any> = {
      'meeting_summary': Users,
      'follow_up_questions': MessageSquare,
      'topic_summary': Brain,
      'sentiment_analysis': Zap,
      'fact_check': CheckCircle,
      'gaps_reasoning': AlertCircle,
      'brainstorming': MessageSquare,
      'scqa': Brain,
      'hypothesis_driven': Brain,
      'first_principles': Brain,
      'company_fit': CheckCircle,
      'answer_question': MessageSquare,
      'practitioner_insights': Brain,
      'issue_tree': Brain,
      'reframing': Brain
    };
    return iconMap[promptId] || Brain;
  };

  // WebSocket connection
  const {
    connectionStatus,
    recordingStatus,
    startRecording,
    stopRecording,
    pauseRecording,
    transcribeBuffer,
    transcribeLast30,
    analyzeTranscript,
    onMessage,
    connect,
    getAudioBuffer,
    loadTestAudio
  } = useWebSocket();

  // UI state
  const [isMuted, setIsMuted] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [status, setStatus] = useState<'idle' | 'recording' | 'processing' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('Connecting...');
  
  // Data state
  const [transcriptionSegments, setTranscriptionSegments] = useState<TranscriptionSegment[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [prompts, setPrompts] = useState<PromptInfo[]>([]);
  const [promptsLoading, setPromptsLoading] = useState(true);
  
  // Current streaming analysis
  const [currentAnalysis, setCurrentAnalysis] = useState<AnalysisResult | null>(null);
  
  // Audio playback
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  
  const recordingInterval = useRef<NodeJS.Timeout>();

  // Load prompts on mount
  useEffect(() => {
    const loadPrompts = async () => {
      console.log('🔄 Loading prompts from API...');
      try {
        const response = await apiClient.getPrompts();
        console.log('✅ Prompts loaded:', response.prompts.length);
        setPrompts(response.prompts);
        setPromptsLoading(false);
      } catch (error) {
        console.error('❌ Failed to load prompts:', error);
        setPromptsLoading(false);
      }
    };

    loadPrompts();
  }, []);

  // Update status based on connection and recording state
  useEffect(() => {
    if (connectionStatus.isConnecting) {
      setStatus('processing');
      setStatusMessage('Connecting to server...');
    } else if (!connectionStatus.isConnected) {
      setStatus('error');
      setStatusMessage(connectionStatus.error || 'Disconnected - Check server');
    } else if (recordingStatus.is_recording) {
      setStatus('recording');
      setStatusMessage(recordingStatus.is_paused ? 'Recording paused' : 'Recording audio...');
    } else {
      setStatus('idle');
      setStatusMessage('Ready to record');
    }
  }, [connectionStatus, recordingStatus]);

  // Recording timer effect
  useEffect(() => {
    if (recordingStatus.is_recording && !recordingStatus.is_paused) {
      recordingInterval.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } else {
      if (recordingInterval.current) clearInterval(recordingInterval.current);
      if (!recordingStatus.is_recording) {
        setRecordingTime(0);
      }
    }

    return () => {
      if (recordingInterval.current) clearInterval(recordingInterval.current);
    };
  }, [recordingStatus.is_recording, recordingStatus.is_paused]);

  // WebSocket message handlers
  useEffect(() => {
    const unsubscribeTranscription = onMessage('transcription_result', (data) => {
      const newSegment: TranscriptionSegment = {
        id: Date.now().toString(),
        text: data.transcript,
        timestamp: data.timestamp * 1000, // Convert to milliseconds
        duration_type: data.duration_type
      };
      setTranscriptionSegments(prev => [...prev, newSegment]);
      setStatus('idle');
      setStatusMessage('Transcription complete');
    });

    const unsubscribeAnalysis = onMessage('analysis_result', (data) => {
      if (currentAnalysis) {
        // Finalize the streaming analysis
        setAnalyses(prev => [...prev, {
          type: data.analysis_type,
          content: data.result,
          timestamp: data.timestamp * 1000,
          isStreaming: false
        }]);
        setCurrentAnalysis(null);
      }
      setStatus('idle');
      setStatusMessage('Analysis complete');
    });

    const unsubscribeStream = onMessage('stream_chunk', (data) => {
      if (currentAnalysis) {
        // Update streaming content
        setCurrentAnalysis(prev => prev ? {
          ...prev,
          content: prev.content + data.chunk
        } : null);
      } else {
        // Start new streaming analysis
        setCurrentAnalysis({
          type: data.analysis_type,
          content: data.chunk,
          timestamp: Date.now(),
          isStreaming: true
        });
      }
    });

    const unsubscribeStatus = onMessage('status_update', (data) => {
      setStatusMessage(data.message);
    });

    const unsubscribeError = onMessage('error', (data) => {
      setStatus('error');
      setStatusMessage(data.message);
      setCurrentAnalysis(null);
    });

    const unsubscribeAudioBuffer = onMessage('audio_buffer_result', (data) => {
      if (data.audio_data) {
        // Convert base64 audio data to blob URL
        try {
          const audioBlob = new Blob([Uint8Array.from(atob(data.audio_data), c => c.charCodeAt(0))], { 
            type: 'audio/wav' 
          });
          const url = URL.createObjectURL(audioBlob);
          setAudioUrl(url);
          setStatus('idle');
          setStatusMessage('Audio buffer ready to play');
        } catch (error) {
          console.error('Failed to process audio buffer:', error);
          setStatus('error');
          setStatusMessage('Failed to load audio buffer');
        }
      } else {
        setStatus('error');
        setStatusMessage('No audio data in buffer');
      }
    });

    return () => {
      unsubscribeTranscription();
      unsubscribeAnalysis();
      unsubscribeStream();
      unsubscribeStatus();
      unsubscribeError();
      unsubscribeAudioBuffer();
    };
  }, [onMessage, currentAnalysis]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleStartRecording = () => {
    startRecording();
  };

  const handleStopRecording = () => {
    stopRecording();
  };

  const handlePauseRecording = () => {
    pauseRecording();
  };

  const handleTranscribeBuffer = () => {
    setStatus('processing');
    transcribeBuffer();
  };

  const handleTranscribeLast30s = () => {
    setStatus('processing');
    transcribeLast30();
  };

  const handleAnalyze = (promptId: string, promptLabel: string) => {
    if (transcriptionSegments.length === 0) {
      setStatus('error');
      setStatusMessage('No transcript available for analysis');
      return;
    }

    // Get the latest transcript or combine all transcripts
    const fullTranscript = transcriptionSegments
      .map(segment => segment.text)
      .join(' ');

    if (!fullTranscript.trim()) {
      setStatus('error');
      setStatusMessage('No transcript content available');
      return;
    }

    setStatus('processing');
    setStatusMessage(`Generating ${promptLabel} analysis...`);
    analyzeTranscript(fullTranscript, promptId, promptLabel);
  };

  const handlePlayBuffer = () => {
    setStatus('processing');
    setStatusMessage('Loading audio buffer...');
    getAudioBuffer();
  };

  const handleLoadTestAudio = () => {
    setStatus('processing');
    setStatusMessage('Loading test audio...');
    loadTestAudio();
  };

  const handlePlayAudio = () => {
    if (audioRef.current && audioUrl) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play();
        setIsPlaying(true);
      }
    }
  };

  const handleAudioEnded = () => {
    setIsPlaying(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col">
      {/* Top Navbar */}
      <div className="border-b border-white/10 bg-slate-900/50 backdrop-blur-sm p-4">
        <div className="flex items-center justify-between max-w-screen-xl mx-auto">
          {/* Left: Darin Branding */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-gradient-to-br from-teal-400 to-blue-500 rounded-xl flex items-center justify-center">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-teal-400 to-blue-400 bg-clip-text text-transparent">
                Darin
              </h1>
              <p className="text-xs text-slate-400">AI Audio Assistant</p>
            </div>
          </div>

          {/* Center: Recording Controls and Buffer */}
          <div className="flex items-center space-x-6">
            {/* Recording Controls */}
            <div className="flex items-center space-x-3">
              <div className="h-4 w-16 opacity-70">
                <AudioVisualizer isRecording={recordingStatus.is_recording && !recordingStatus.is_paused} />
              </div>
              
              <button
                onClick={recordingStatus.is_recording ? handleStopRecording : handleStartRecording}
                disabled={!connectionStatus.isConnected}
                className={`p-3 rounded-full transition-all duration-200 disabled:opacity-50 ${
                  recordingStatus.is_recording 
                    ? 'bg-red-500 hover:bg-red-600' 
                    : 'bg-gradient-to-r from-teal-500 to-blue-500 hover:scale-105'
                }`}
              >
                {recordingStatus.is_recording ? (
                  <Square className="w-5 h-5 text-white" />
                ) : (
                  <Mic className="w-5 h-5 text-white" />
                )}
              </button>
              
              {recordingStatus.is_recording && (
                <button
                  onClick={handlePauseRecording}
                  className="p-3 bg-yellow-500 hover:bg-yellow-600 rounded-full transition-colors duration-200"
                  disabled={!connectionStatus.isConnected}
                >
                  {recordingStatus.is_paused ? (
                    <Play className="w-4 h-4 text-white" />
                  ) : (
                    <Pause className="w-4 h-4 text-white" />
                  )}
                </button>
              )}
            </div>

            {/* Buffer Info */}
            <div className="bg-slate-800/50 rounded-lg px-4 py-2">
              <div className="flex items-center space-x-4">
                <div className="text-sm font-mono text-white">
                  {formatTime(recordingTime)}
                </div>
                <div className="text-xs text-slate-400">
                  Buffer: {formatTime(recordingStatus.buffer_duration)} / {formatTime(recordingStatus.buffer_max_duration)}
                </div>
                <div className="w-20 bg-slate-700 rounded-full h-2">
                  <div 
                    className="bg-gradient-to-r from-teal-500 to-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(recordingStatus.buffer_duration / recordingStatus.buffer_max_duration) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Right: Status */}
          <div className="flex items-center space-x-4">
            <StatusIndicator 
              status={status} 
              message={statusMessage} 
              isConnected={connectionStatus.isConnected} 
            />
            
            {!connectionStatus.isConnected && (
              <button
                onClick={() => connect()}
                disabled={connectionStatus.isConnecting}
                className="px-3 py-1 bg-red-600 hover:bg-red-700 text-xs rounded disabled:opacity-50"
              >
                {connectionStatus.isConnecting ? 'Connecting...' : 'Retry'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex">
        {/* Left Sidebar - Controls */}
        <div className="w-80 max-w-sm border-r border-white/10 bg-slate-900/50 backdrop-blur-sm flex flex-col flex-shrink-0">
          {/* Sidebar Content */}
          <div className="flex-1 p-6 space-y-6 overflow-y-auto">
            {/* Test Audio */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-slate-300">Test Mode</h4>
              <button
                onClick={handleLoadTestAudio}
                disabled={status === 'processing' || !connectionStatus.isConnected}
                className="w-full py-2 px-4 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center space-x-2"
              >
                <Upload className="w-4 h-4" />
                <span>Load Test Audio</span>
              </button>
            </div>
            
            {/* Buffer Controls */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-slate-300">Buffer Actions</h4>
              <div className="space-y-2">
                <button
                  onClick={handleTranscribeBuffer}
                  disabled={status === 'processing' || !connectionStatus.isConnected}
                  className="w-full py-2 px-4 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center space-x-2"
                >
                  <FileText className="w-4 h-4" />
                  <span>Transcribe Buffer</span>
                </button>
                
                <button
                  onClick={handleTranscribeLast30s}
                  disabled={status === 'processing' || !connectionStatus.isConnected}
                  className="w-full py-2 px-4 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center space-x-2"
                >
                  <Clock className="w-4 h-4" />
                  <span>Last 30s</span>
                </button>
                
                <button
                  onClick={handlePlayBuffer}
                  disabled={status === 'processing' || !connectionStatus.isConnected}
                  className="w-full py-2 px-4 bg-teal-700 hover:bg-teal-600 disabled:opacity-50 rounded-lg transition-colors flex items-center justify-center space-x-2"
                >
                  <PlayCircle className="w-4 h-4" />
                  <span>Play Buffer</span>
                </button>
              </div>
            </div>
            
            {/* Audio Playback */}
            {audioUrl && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-slate-300">Playback</h4>
                <button
                  onClick={handlePlayAudio}
                  className="w-full py-2 px-4 bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors flex items-center justify-center space-x-2"
                >
                  {isPlaying ? (
                    <>
                      <Pause className="w-4 h-4" />
                      <span>Pause</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      <span>Play</span>
                    </>
                  )}
                </button>
                <audio ref={audioRef} src={audioUrl} onEnded={handleAudioEnded} className="hidden" />
              </div>
            )}
            
            {/* AI Analysis Prompts */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-slate-300">AI Analysis</h4>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {promptsLoading ? (
                  <div className="text-center py-4 text-slate-500">Loading prompts...</div>
                ) : prompts.length === 0 ? (
                  <div className="text-center py-4 text-slate-500">No prompts available</div>
                ) : (
                  prompts.map((prompt) => {
                    const Icon = getIconForPrompt(prompt.id);
                    return (
                      <button
                        key={prompt.id}
                        onClick={() => handleAnalyze(prompt.id, prompt.button_text)}
                        className="w-full p-2 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-white/5 hover:border-white/10 transition-all duration-200 group text-left"
                        title={prompt.output_title}
                      >
                        <div className="flex items-center space-x-2">
                          <Icon className="w-3 h-3 text-slate-400 group-hover:text-teal-400 transition-colors flex-shrink-0" />
                          <span className="text-xs text-slate-300 group-hover:text-white transition-colors">
                            {prompt.button_text}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
        
        {/* Right Content Area */}
        <div className="flex-1 flex flex-col">
          {/* Transcription Area (Top) */}
          <div className="flex-1 p-6">
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 h-full flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
                  <FileText className="w-5 h-5" />
                  <span>Live Transcription</span>
                </h3>
                <button className="p-2 hover:bg-white/10 rounded-lg transition-colors duration-200">
                  <Download className="w-4 h-4 text-slate-400" />
                </button>
              </div>
              
              <div className="flex-1 overflow-y-auto space-y-3 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent">
                {transcriptionSegments.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-slate-500">
                    <div className="text-center">
                      <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
                      <p>Transcription will appear here...</p>
                    </div>
                  </div>
                ) : (
                  transcriptionSegments.map((segment) => (
                    <div key={segment.id} className="group">
                      <div className="flex items-start space-x-3">
                        <div className="text-xs text-slate-500 mt-1 min-w-[60px]">
                          {new Date(segment.timestamp).toLocaleTimeString([], { 
                            hour: '2-digit', 
                            minute: '2-digit',
                            second: '2-digit'
                          })}
                        </div>
                        <div className="flex-1">
                          {segment.speaker && (
                            <div className="text-xs text-teal-400 mb-1 font-medium">
                              {segment.speaker}
                            </div>
                          )}
                          <p className="text-slate-200 leading-relaxed group-hover:text-white transition-colors duration-200">
                            {segment.text}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
          
          {/* Analysis Results Area (Bottom) */}
          <div className="flex-1 p-6 pt-0">
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 h-full flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
                  <Brain className="w-5 h-5" />
                  <span>Analysis Results</span>
                </h3>
              </div>
              
              <div className="flex-1 overflow-y-auto space-y-3 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent">
                {[...analyses, ...(currentAnalysis ? [currentAnalysis] : [])].length === 0 ? (
                  <div className="flex items-center justify-center h-full text-slate-500">
                    <div className="text-center">
                      <Brain className="w-12 h-12 mx-auto mb-3 opacity-50" />
                      <p>Analysis results will appear here...</p>
                    </div>
                  </div>
                ) : (
                  [...analyses, ...(currentAnalysis ? [currentAnalysis] : [])].map((analysis, index) => (
                    <div key={index} className={`rounded-xl p-4 border ${
                      analysis.isStreaming ? 'border-teal-400/30 bg-teal-900/10' : 'border-white/5 bg-slate-700/30'
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm font-medium text-teal-400 capitalize">
                            {analysis.type}
                          </span>
                          {analysis.isStreaming && (
                            <div className="flex items-center space-x-1">
                              <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse"></div>
                              <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse delay-75"></div>
                              <div className="w-1 h-1 bg-teal-400 rounded-full animate-pulse delay-150"></div>
                            </div>
                          )}
                        </div>
                        <span className="text-xs text-slate-500">
                          {new Date(analysis.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-slate-200 text-sm leading-relaxed">
                        {analysis.content}
                        {analysis.isStreaming && (
                          <span className="inline-block w-2 h-4 bg-teal-400 ml-1 animate-pulse"></span>
                        )}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;