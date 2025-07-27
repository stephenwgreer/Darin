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
  VolumeX
} from 'lucide-react';

interface TranscriptionSegment {
  id: string;
  text: string;
  timestamp: number;
  speaker?: string;
}

interface AnalysisResult {
  type: string;
  content: string;
  timestamp: number;
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

const StatusIndicator = ({ status, message }: { status: 'idle' | 'recording' | 'processing' | 'error'; message: string }) => {
  const getStatusColor = () => {
    switch (status) {
      case 'recording': return 'text-red-400';
      case 'processing': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      default: return 'text-slate-400';
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'recording': return <div className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />;
      case 'processing': return <div className="w-2 h-2 bg-yellow-400 rounded-full animate-spin" />;
      case 'error': return <AlertCircle className="w-4 h-4 text-red-400" />;
      default: return <div className="w-2 h-2 bg-slate-400 rounded-full" />;
    }
  };

  return (
    <div className="flex items-center space-x-2">
      {getStatusIcon()}
      <span className={`text-sm ${getStatusColor()}`}>{message}</span>
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

const AnalysisPanel = ({ analyses, onAnalyze }: { 
  analyses: AnalysisResult[]; 
  onAnalyze: (type: string) => void;
}) => {
  const analysisTypes = [
    { id: 'summary', label: 'Meeting Summary', icon: Users },
    { id: 'questions', label: 'Follow-up Questions', icon: MessageSquare },
    { id: 'topics', label: 'Topic Analysis', icon: Brain },
    { id: 'sentiment', label: 'Sentiment Analysis', icon: Zap },
    { id: 'facts', label: 'Fact Checking', icon: CheckCircle },
    { id: 'gaps', label: 'Gap Analysis', icon: AlertCircle }
  ];

  return (
    <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 h-96">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
          <Brain className="w-5 h-5" />
          <span>AI Analysis</span>
        </h3>
      </div>
      
      <div className="grid grid-cols-2 gap-3 mb-6">
        {analysisTypes.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onAnalyze(id)}
            className="p-3 bg-slate-700/50 hover:bg-slate-700 rounded-xl border border-white/5 hover:border-white/10 transition-all duration-200 group"
          >
            <div className="flex items-center space-x-2">
              <Icon className="w-4 h-4 text-slate-400 group-hover:text-teal-400 transition-colors duration-200" />
              <span className="text-sm text-slate-300 group-hover:text-white transition-colors duration-200">
                {label}
              </span>
            </div>
          </button>
        ))}
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
            <div key={index} className="bg-slate-700/30 rounded-xl p-4 border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-teal-400 capitalize">
                  {analysis.type}
                </span>
                <span className="text-xs text-slate-500">
                  {new Date(analysis.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-slate-200 text-sm leading-relaxed">
                {analysis.content}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [bufferTime, setBufferTime] = useState(0);
  const [status, setStatus] = useState<'idle' | 'recording' | 'processing' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('Ready to record');
  
  const [transcriptionSegments, setTranscriptionSegments] = useState<TranscriptionSegment[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  
  const recordingInterval = useRef<NodeJS.Timeout>();
  const bufferInterval = useRef<NodeJS.Timeout>();

  useEffect(() => {
    if (isRecording && !isPaused) {
      recordingInterval.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
      
      bufferInterval.current = setInterval(() => {
        setBufferTime(prev => Math.min(prev + 1, 180)); // 3 minute max buffer
      }, 1000);
    } else {
      if (recordingInterval.current) clearInterval(recordingInterval.current);
      if (bufferInterval.current) clearInterval(bufferInterval.current);
    }

    return () => {
      if (recordingInterval.current) clearInterval(recordingInterval.current);
      if (bufferInterval.current) clearInterval(bufferInterval.current);
    };
  }, [isRecording, isPaused]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleStartRecording = () => {
    setIsRecording(true);
    setIsPaused(false);
    setStatus('recording');
    setStatusMessage('Recording audio...');
    setRecordingTime(0);
    setBufferTime(0);
  };

  const handleStopRecording = () => {
    setIsRecording(false);
    setIsPaused(false);
    setStatus('idle');
    setStatusMessage('Recording stopped');
    setRecordingTime(0);
    setBufferTime(0);
  };

  const handlePauseRecording = () => {
    setIsPaused(!isPaused);
    setStatus(isPaused ? 'recording' : 'idle');
    setStatusMessage(isPaused ? 'Recording resumed' : 'Recording paused');
  };

  const handleTranscribeBuffer = async () => {
    setStatus('processing');
    setStatusMessage('Transcribing audio buffer...');
    
    // Simulate transcription process
    setTimeout(() => {
      const newSegment: TranscriptionSegment = {
        id: Date.now().toString(),
        text: "This is a simulated transcription of the audio buffer. In a real implementation, this would be the actual transcribed text from the recorded audio using a service like Deepgram or OpenAI Whisper.",
        timestamp: Date.now(),
        speaker: "Speaker 1"
      };
      
      setTranscriptionSegments(prev => [...prev, newSegment]);
      setStatus('idle');
      setStatusMessage('Transcription complete');
    }, 2000);
  };

  const handleTranscribeLast30s = async () => {
    setStatus('processing');
    setStatusMessage('Transcribing last 30 seconds...');
    
    setTimeout(() => {
      const newSegment: TranscriptionSegment = {
        id: Date.now().toString(),
        text: "This is a transcription of the last 30 seconds of audio. The system maintains a rolling buffer to capture recent conversations.",
        timestamp: Date.now(),
        speaker: "Speaker 2"
      };
      
      setTranscriptionSegments(prev => [...prev, newSegment]);
      setStatus('idle');
      setStatusMessage('Recent transcription complete');
    }, 1500);
  };

  const handleAnalyze = async (type: string) => {
    setStatus('processing');
    setStatusMessage(`Generating ${type} analysis...`);
    
    const analysisContent = {
      summary: "Key discussion points: Project timeline, resource allocation, and next steps. Main decisions made include moving forward with the proposed solution and scheduling follow-up meetings.",
      questions: "1. What are the specific resource requirements? 2. When is the expected completion date? 3. Who will be responsible for each deliverable?",
      topics: "Main topics discussed: Project management, timeline planning, resource allocation, team coordination, and risk assessment.",
      sentiment: "Overall sentiment: Positive and collaborative. Participants showed enthusiasm for the project with constructive engagement throughout the discussion.",
      facts: "All mentioned dates and figures have been verified. Project timeline aligns with company standards and resource availability has been confirmed.",
      gaps: "Potential gaps identified: Need for clearer communication protocols and more detailed risk mitigation strategies."
    };
    
    setTimeout(() => {
      const newAnalysis: AnalysisResult = {
        type,
        content: analysisContent[type as keyof typeof analysisContent] || "Analysis completed successfully.",
        timestamp: Date.now()
      };
      
      setAnalyses(prev => [...prev, newAnalysis]);
      setStatus('idle');
      setStatusMessage('Analysis complete');
    }, 3000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-white/10 bg-slate-900/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-br from-teal-400 to-blue-500 rounded-xl flex items-center justify-center">
                <MessageSquare className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-teal-400 to-blue-400 bg-clip-text text-transparent">
                  Darin
                </h1>
                <p className="text-xs text-slate-400">AI Conversation Assistant</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              <StatusIndicator status={status} message={statusMessage} />
              <button className="p-2 hover:bg-white/10 rounded-lg transition-colors duration-200">
                <Settings className="w-5 h-5 text-slate-400" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Recording Controls */}
        <div className="mb-8">
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-8">
            <div className="flex flex-col lg:flex-row items-center justify-between space-y-6 lg:space-y-0">
              {/* Audio Visualizer */}
              <div className="flex-1">
                <AudioVisualizer isRecording={isRecording && !isPaused} />
              </div>
              
              {/* Recording Info */}
              <div className="text-center space-y-2">
                <div className="text-3xl font-mono text-white">
                  {formatTime(recordingTime)}
                </div>
                <div className="text-sm text-slate-400">
                  Buffer: {formatTime(bufferTime)} / 03:00
                </div>
                <div className="w-64 bg-slate-700 rounded-full h-2">
                  <div 
                    className="bg-gradient-to-r from-teal-500 to-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(bufferTime / 180) * 100}%` }}
                  />
                </div>
              </div>
              
              {/* Control Buttons */}
              <div className="flex items-center space-x-4">
                <button
                  onClick={isMuted ? () => setIsMuted(false) : () => setIsMuted(true)}
                  className="p-3 bg-slate-700 hover:bg-slate-600 rounded-xl transition-colors duration-200"
                >
                  {isMuted ? (
                    <VolumeX className="w-5 h-5 text-slate-400" />
                  ) : (
                    <Volume2 className="w-5 h-5 text-slate-400" />
                  )}
                </button>
                
                {isRecording && (
                  <button
                    onClick={handlePauseRecording}
                    className="p-3 bg-yellow-500 hover:bg-yellow-600 rounded-xl transition-colors duration-200"
                  >
                    {isPaused ? (
                      <Play className="w-5 h-5 text-white" />
                    ) : (
                      <Pause className="w-5 h-5 text-white" />
                    )}
                  </button>
                )}
                
                <button
                  onClick={isRecording ? handleStopRecording : handleStartRecording}
                  className={`p-4 rounded-xl transition-all duration-200 ${
                    isRecording 
                      ? 'bg-red-500 hover:bg-red-600' 
                      : 'bg-gradient-to-r from-teal-500 to-blue-500 hover:shadow-lg hover:shadow-teal-500/25 hover:scale-105'
                  }`}
                >
                  {isRecording ? (
                    <Square className="w-6 h-6 text-white" />
                  ) : (
                    <Mic className="w-6 h-6 text-white" />
                  )}
                </button>
              </div>
            </div>
            
            {/* Transcription Controls */}
            <div className="flex flex-col sm:flex-row gap-4 mt-6 pt-6 border-t border-white/10">
              <button
                onClick={handleTranscribeBuffer}
                disabled={status === 'processing'}
                className="flex-1 py-3 px-6 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
              >
                <FileText className="w-4 h-4" />
                <span>Transcribe Buffer</span>
              </button>
              
              <button
                onClick={handleTranscribeLast30s}
                disabled={status === 'processing'}
                className="flex-1 py-3 px-6 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
              >
                <Clock className="w-4 h-4" />
                <span>Transcribe Last 30s</span>
              </button>
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid lg:grid-cols-2 gap-8">
          <TranscriptionPanel segments={transcriptionSegments} />
          <AnalysisPanel analyses={analyses} onAnalyze={handleAnalyze} />
        </div>
      </div>
    </div>
  );
}

export default App;