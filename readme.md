# Darin Audio Assistant 🎙️

A powerful desktop application that records, transcribes, and analyzes conversations in real-time using advanced AI capabilities. Built with PyQt6 and Claude AI, Darin acts as your intelligent note-taking assistant for meetings, interviews, and discussions.

![Darin Audio Assistant](assets/Darin_Round.png)

## ✨ Features

- **Real-time Audio Recording**: Continuously record audio with a 3-minute rolling buffer
- **Live Transcription**: Convert speech to text using Deepgram's advanced speech recognition
- **AI-Powered Analysis**: Generate insights using Claude AI with features like:
  - Meeting summaries
  - Follow-up questions
  - Topic extraction
  - Sentiment analysis
  - Fact checking
  - Gap analysis
  - Brainstorming suggestions
  - Company/domain-specific insights

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- PyQt6
- Sound device support for audio recording
- API keys for Deepgram and Anthropic (Claude)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/audio_test.git
cd audio_test
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your API keys:

**Copy the example environment file:**
```bash
cp .env.example .env
```

**Edit `.env` and add your actual API keys:**
```env
ANTHROPIC_API_KEY=sk-ant-api03-your_actual_anthropic_key_here
DEEPGRAM_API_KEY=your_actual_deepgram_key_here
```

**Get your API keys from:**
- Anthropic (Claude AI): https://console.anthropic.com/
- Deepgram (Transcription): https://console.deepgram.com/

**Important:** The application validates API keys at startup and will show a clear error message if keys are missing or invalid. Never commit your `.env` file to version control.

### Running the Application

```bash
python main.py
```

## 🎯 Usage

1. **Recording**
   - Click the "Record" button to start/stop recording
   - The application maintains a 3-minute rolling buffer

2. **Transcription**
   - Click "Transcribe Buffer" to transcribe the entire buffer
   - Use "Transcribe Last 30s" for recent content only

3. **Analysis**
   - Select from various analysis options:
     - Meeting Summary
     - Follow-up Questions
     - Topic Analysis
     - Sentiment Analysis
     - Fact Checking
     - and more...

## 🏗️ Project Structure

```
audio_test/
├── api/                # API client implementations
├── audio/             # Audio recording and processing
├── assets/            # Images and static resources
├── prompts/           # AI prompt templates
├── ui/                # PyQt6 UI components
├── main.py           # Application entry point
├── config.py         # Configuration settings
└── utils.py          # Utility functions
```

## 🛠️ Technical Details

- **Frontend**: PyQt6 for the desktop interface
- **Audio Processing**: sounddevice and numpy for audio handling
- **Speech Recognition**: Deepgram API
- **AI Analysis**: Claude (Anthropic) API
- **Styling**: Custom CSS for rich text formatting

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Deepgram](https://deepgram.com/) for speech-to-text capabilities
- [Anthropic](https://www.anthropic.com/) for Claude AI integration
- [PyQt](https://www.riverbankcomputing.com/software/pyqt/) for the GUI framework

## 📧 Contact

For questions and support, please open an issue in the GitHub repository.

---

Made with ❤️ by [Your Name/Organization]