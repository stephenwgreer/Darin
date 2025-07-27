/**
 * API Client for FastAPI Backend
 * Handles HTTP requests to REST endpoints
 */

export interface PromptInfo {
  id: string;
  button_text: string;
  output_title: string;
  template_type: string;
}

export interface PromptCategory {
  transcript_processing: PromptInfo[];
  analysis: PromptInfo[];
  logic_frameworks: PromptInfo[];
  specialized: PromptInfo[];
}

export interface PromptStats {
  total_prompts: number;
  categories: Record<string, number>;
  template_types: string[];
  prompt_ids: string[];
}

export interface PromptsResponse {
  prompts: PromptInfo[];
  categories: PromptCategory;
  stats: PromptStats;
}

export interface HealthResponse {
  status: string;
  components: {
    audio_recorder: boolean;
    api_clients: boolean;
    websocket_manager: boolean;
    frontend_built: boolean;
  };
}

export interface ApiStatusResponse {
  audio: {
    is_recording: boolean;
    is_paused: boolean;
    buffer_duration: number;
    sample_rate: number;
  };
  apis: {
    anthropic_configured: boolean;
    deepgram_configured: boolean;
  };
  websocket: any;
  prompts: any;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  /**
   * Get available prompts and categories
   */
  async getPrompts(): Promise<PromptsResponse> {
    return this.request<PromptsResponse>('/api/prompts');
  }

  /**
   * Get backend health status
   */
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  /**
   * Get detailed API status
   */
  async getStatus(): Promise<ApiStatusResponse> {
    return this.request<ApiStatusResponse>('/api/status');
  }

  /**
   * Check if backend is reachable
   */
  async ping(): Promise<boolean> {
    try {
      await this.getHealth();
      return true;
    } catch {
      return false;
    }
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;