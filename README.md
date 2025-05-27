# Change Analyzer MCP Server

An Agent-to-Agent (A2A) compatible server for Git repository analysis.

## Features

- Analyze Git repositories for changes
- Provide metrics and statistics about repositories
- Analyze directory structures
- A2A protocol integration for agent communication

## Installation

### Prerequisites

- Python 3.9+
- Redis (for state management)

### Using pip

```bash
pip install mcp-change-analyzer
```

### From source

```bash
git clone https://github.com/your-org/mcp-change-analyzer.git
cd mcp-change-analyzer
pip install -e .
```

## Usage

### Starting the server

```bash
mcp-change-analyzer serve --config config/server.yaml
```

### Using the A2A API

Send A2A requests to the server's RPC endpoint:

```python
from a2a.client import A2AClient

async def analyze_repo():
    client = A2AClient("change-analyzer", base_url="http://localhost:8081")
    response = await client.request({
        "method": "analyze_repository",
        "params": {
            "repo_path": "/path/to/repo"
        }
    })
    print(response)
```

## Configuration

The server is configured using YAML files. See `config/server.yaml` for an example.

## License

MIT
