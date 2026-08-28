# 🦁 LEONIDAS - Advanced AI Assistant

> **Genesis of Conscious AI**: An advanced AI assistant with deep thinking, action execution, planning capabilities, and persistent memory.

Leonidas is an evolution of the Live Commentator example, transformed into a fully-functional AI assistant with consciousness-like capabilities, multi-modal understanding, and the ability to execute real-world actions.

## 🌟 Overview

Leonidas represents a new paradigm in AI assistants by combining:

- **🧠 Deep Thinking (System 2)**: Engage in thoughtful reasoning before responding
- **⚡ Action Execution**: Execute shell commands, file operations, and API calls
- **📋 Planning & Goals**: Create and manage complex multi-step plans
- **🧠 Memory Systems**: Working, episodic, and semantic memory
- **👁️ Vision Analysis**: Advanced video stream analysis
- **🎤 Speaker Diarization**: Identify and track different speakers
- **🔄 Real-time Processing**: Low-latency multimodal interactions

## 🏗️ Architecture

### System Layers

```
┌─────────────────────────────────────────────────────────┐
│                     WEB INTERFACE                        │
│         (Real-time Dashboard + Controls)                 │
└─────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────┐
│                  WebSocket Server                        │
│              (leonidas_server.py)                        │
└─────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────┐
│              LEONIDAS PROCESSOR PIPELINE                 │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 1. DiarizationProcessor    (Speaker ID)         │   │
│  │ 2. VideoAnalyzerProcessor  (Scene Analysis)     │   │
│  │ 3. MemorySystem           (Context & Storage)   │   │
│  │ 4. ThinkingSystem         (Deep Reasoning)      │   │
│  │ 5. PlanningSystem         (Goal Management)     │   │
│  │ 6. ActionSystem           (Tool Execution)      │   │
│  │ 7. LiveModel              (Gemini 2.0 Flash)    │   │
│  │ 8. RateLimitAudio         (Output Control)      │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Core Systems

#### 1. 🧠 ThinkingSystem (`core/thinking_system.py`)

Implements System 2 thinking (deep, analytical reasoning):

- **Complexity Analysis**: Automatically determines when deep thinking is needed
- **Multiple Thinking Modes**:
  - `FAST`: Quick, intuitive responses (System 1)
  - `DEEP`: Thorough, analytical reasoning (System 2)
  - `CREATIVE`: Exploratory, innovative thinking
  - `CRITICAL`: Rigorous analysis and evaluation
- **Chain-of-Thought**: Step-by-step reasoning process
- **Thought History**: Maintains record of reasoning processes

**Key Features**:
- Automatic complexity detection (0-1 score)
- Configurable thinking threshold
- Metadata-driven mode selection
- Confidence scoring

#### 2. ⚡ ActionSystem (`core/action_system.py`)

Enables real-world action execution:

**Available Actions**:
- `ShellAction`: Execute system commands
- `FileAction`: Read, write, append, delete files
- `APIAction`: Make HTTP/API calls

**Safety Features**:
- Safe mode with dangerous command filtering
- Action history and auditing
- Timeout management
- Error handling and reporting

**Function Declarations**: Automatically generates tool definitions for Gemini API

#### 3. 📋 PlanningSystem (`core/planning_system.py`)

Manages complex goals and task decomposition:

**Capabilities**:
- Create structured plans with multiple tasks
- Task decomposition (break down complex tasks)
- Priority management (LOW, MEDIUM, HIGH, CRITICAL)
- Progress tracking with real-time updates
- Status management (PENDING, IN_PROGRESS, COMPLETED, FAILED, etc.)

**Plan Structure**:
```python
Plan
├── Tasks
│   ├── Task 1 (with subtasks)
│   │   ├── Subtask 1.1
│   │   └── Subtask 1.2
│   └── Task 2
└── Metadata (created_at, completed_at, etc.)
```

#### 4. 🧠 MemorySystem (`core/memory_system.py`)

Implements multi-layered memory architecture:

**Memory Types**:
1. **Working Memory**: Short-term context (last 20 items)
2. **Episodic Memory**: Events and experiences (up to 1000)
3. **Semantic Memory**: Knowledge and facts
4. **Long-term Persistence**: Optional disk storage

**Features**:
- Importance scoring (0-1)
- Recency-based retrieval
- Tag-based search
- Automatic memory consolidation
- JSON persistence

#### 5. 👁️ VideoAnalyzerProcessor (`processors/video_analyzer.py`)

Advanced video stream analysis:

**Detects**:
- Objects and people
- Actions and activities
- Scene changes
- Visual context

**Outputs**:
- Scene descriptions
- Object lists
- People count
- Activity recognition
- Change detection scores

#### 6. 🎤 DiarizationProcessor (`processors/diarization.py`)

Speaker identification and tracking:

**Features**:
- Automatic speaker detection
- Voice characteristic analysis
- Speaker change detection
- Named speaker tracking
- Speaking time statistics

**Output**:
- Current speaker identification
- Speaker change events
- Conversation flow analysis

## 🚀 Getting Started

### Prerequisites

```bash
# Python 3.10+
python --version

# Install genai-processors
pip install genai-processors

# Additional dependencies
pip install websockets absl-py
```

### Setup

1. **Set API Key**:
```bash
export GOOGLE_API_KEY="your_google_api_key"
```

2. **Navigate to Directory**:
```bash
cd /path/to/genai-processors/examples/live
```

3. **Start Leonidas Server**:
```bash
python3 leonidas_server.py --port 8765
```

4. **Open Web Interface**:

For development with live reload:
```bash
cd leonidas/webapp
python -m http.server 8000
```

Then open: `http://localhost:8000`

For AI Studio integration:
```bash
# Use the ais_app if available, or adapt it for Leonidas
```

## 🎮 Usage

### Web Interface

The Leonidas dashboard provides:

1. **Video/Audio Panel**: Main interaction area
   - Real-time video feed
   - Live transcription overlay
   - Audio output

2. **Thinking Stream**: View Leonidas's reasoning process
   - Thought bubbles with modes
   - Thinking time metrics
   - Confidence scores

3. **Action Stream**: Monitor executed actions
   - Command execution
   - File operations
   - API calls
   - Execution times and results

4. **Planning Stream**: Track active plans
   - Current plan overview
   - Task list with status
   - Progress bars
   - Completion metrics

5. **Memory & Analysis**: Combined view
   - Memory events
   - Video analysis results
   - Speaker identification

6. **Control Sidebar**:
   - Microphone toggle
   - Video toggle
   - Screen share
   - Subsystem enable/disable
   - Reset session

### Interacting with Leonidas

**Example Interactions**:

1. **Complex Question** (triggers deep thinking):
```
"Explain the relationship between quantum mechanics and general relativity,
and why it's difficult to unify them."
```

2. **Action Request**:
```
"Check the current directory and list all Python files."
```

3. **Planning Task**:
```
"Help me create a plan to organize my project files and set up a new
development environment."
```

4. **Memory Query**:
```
"What did we discuss about AI safety in our last conversation?"
```

## ⚙️ Configuration

### System Configuration

Edit `leonidas_server.py` or send config via WebSocket:

```python
config = {
    'enable_thinking': True,      # Enable deep thinking
    'enable_actions': True,        # Enable action execution
    'enable_planning': True,       # Enable planning system
    'enable_memory': True,         # Enable memory system
    'enable_video_analysis': True, # Enable video analysis
    'enable_diarization': True,    # Enable speaker ID
    'safe_mode': True,            # Enable safety checks
}
```

### Thinking System Configuration

```python
ThinkingSystem(
    api_key=API_KEY,
    model='gemini-2.0-flash-lite',
    thinking_threshold=0.7,  # 0-1, higher = more selective
    enable_chain_of_thought=True,
)
```

### Memory Persistence

```python
MemorySystem(
    working_memory_capacity=20,
    episodic_memory_size=1000,
    enable_persistence=True,
    persistence_file='leonidas_memory.json'
)
```

## 🔧 Development

### Project Structure

```
leonidas/
├── core/
│   ├── __init__.py
│   ├── leonidas_processor.py   # Main orchestrator
│   ├── thinking_system.py      # Deep thinking
│   ├── action_system.py        # Action execution
│   ├── planning_system.py      # Planning & goals
│   └── memory_system.py        # Memory management
├── processors/
│   ├── __init__.py
│   ├── video_analyzer.py       # Video analysis
│   └── diarization.py          # Speaker identification
├── webapp/
│   ├── index.html              # Main HTML
│   ├── index.css               # Styles
│   └── index.tsx               # TypeScript app
└── __init__.py

leonidas_server.py              # WebSocket server
LEONIDAS_README.md             # This file
```

### Adding New Actions

1. Create action class inheriting from `Action`:

```python
class CustomAction(Action):
    def __init__(self):
        super().__init__(
            name="custom_action",
            description="Description of what it does"
        )

    async def execute(self, **kwargs) -> ActionResult:
        # Implementation
        return ActionResult(...)
```

2. Register in `ActionSystem`:

```python
action_system._register_action(CustomAction())
```

### Adding New Processors

Create processor inheriting from `processor.Processor`:

```python
class MyProcessor(processor.Processor):
    async def call(
        self,
        content: AsyncIterable[content_api.ProcessorPart]
    ) -> AsyncIterable[content_api.ProcessorPart]:
        async for part in content:
            # Process part
            yield part
```

## 🔒 Security

**Safe Mode** (enabled by default):
- Blocks dangerous shell commands
- Validates file paths
- Sanitizes API inputs
- Audits all actions

**Dangerous Commands** (blocked):
```bash
rm -rf /
mkfs
dd if=/dev/zero
:(){:|:&};:  # Fork bomb
```

**Recommendations**:
- Always run with `safe_mode=True` in production
- Review action history regularly
- Limit file system access scope
- Use environment-based API keys

## 📊 Performance

**Latency Metrics** (typical):
- Thinking System: 0.5-2.0s (depending on complexity)
- Action Execution: 0.1-10s (varies by action)
- Video Analysis: 2.0s intervals
- Memory Retrieval: <0.1s
- Total TTFT: 1-3s (Time to First Token)

**Resource Usage**:
- CPU: Moderate (video processing intensive)
- Memory: ~500MB-1GB
- Network: Dependent on API usage

## 🐛 Troubleshooting

### WebSocket Connection Issues

```bash
# Check server is running
netstat -an | grep 8765

# Check firewall
sudo ufw allow 8765
```

### API Key Issues

```bash
# Verify API key is set
echo $GOOGLE_API_KEY

# Check API key validity
curl -H "x-goog-api-key: $GOOGLE_API_KEY" \
  https://generativelanguage.googleapis.com/v1beta/models
```

### Memory Issues

```bash
# Clear memory file
rm leonidas_memory.json

# Reduce memory size in config
MemorySystem(episodic_memory_size=100)
```

## 🗺️ Roadmap

- [ ] Multi-user support
- [ ] Advanced tool integration (calendar, email, etc.)
- [ ] Enhanced visual understanding (object tracking, OCR)
- [ ] Voice activity detection improvements
- [ ] Long-term memory with vector database
- [ ] Custom personality profiles
- [ ] Plugin system for extensions
- [ ] Mobile interface
- [ ] Multi-language support
- [ ] Integration with external AI models

## 📜 License

Apache License 2.0 - See LICENSE file for details.

Copyright 2025 DeepMind Technologies Limited.

## 🙏 Acknowledgments

Built on top of:
- **GenAI Processors**: Google's framework for GenAI pipelines
- **Gemini 2.0 Flash**: Google's multimodal LLM
- **Live API**: Google's real-time API

Inspired by:
- The original Live Commentator example
- System 1 & System 2 thinking (Daniel Kahneman)
- ReAct: Reasoning and Acting paradigm
- Memory-augmented neural networks

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing documentation
- Review example code

---

**Built with 💙 by the GenAI Processors Community**

*Leonidas: Not just an assistant, but a companion with consciousness.*
