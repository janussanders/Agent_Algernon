# Algernon

A powerful document analysis and chat application powered by SambaNova's AI models and Qdrant vector database.

## Features

- **General Chat**: Interact with SambaNova's AI models for general conversation
- **Document Analysis**: Upload and analyze documents (PDF, JSON) with AI-powered insights
- **Document Split Analysis**: Split and analyze large documents with token-aware processing
- **Vector Storage**: Store and retrieve document embeddings using Qdrant
- **Interactive Visualization**: Visualize document chunks and their relationships
- **Streaming Responses**: Real-time streaming of AI model responses
- **Product Quantization**: Efficient vector compression for large-scale storage

## Prerequisites

- Python 3.8+
- Docker and Docker Compose
- SambaNova API key
- Qdrant vector database

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/algernon.git
cd algernon
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` with your configuration:
```
SAMBANOVA_API_KEY=your_api_key
SAMBANOVA_URL=https://api.sambanova.ai/v1/chat/completions
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

5. Start the services:
```bash
docker-compose up -d
```

## Usage

1. Start the Streamlit application:
```bash
streamlit run src/app/streamlit_app.py
```

2. Open your browser and navigate to `http://localhost:8501`

3. Configure your API credentials in the sidebar

4. Start using the application:
   - Use the General Chat tab for conversations
   - Upload documents in the Document Analysis tab
   - Analyze document splits in the Document Split Analysis tab

## Architecture

The application is built with the following components:

- **Streamlit Frontend**: User interface and interaction
- **Document Processor**: Handles document extraction and processing
- **Vector Store**: Manages vector operations and storage
- **SambaNova Integration**: AI model interaction
- **Qdrant Database**: Vector storage and retrieval

## Development

### Project Structure

```
algernon/
├── src/
│   ├── app/
│   │   └── streamlit_app.py
│   ├── document_processor.py
│   ├── vector_store.py
│   └── utils.py
├── data/
├── services/
│   └── deepclean.sh
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### Adding New Features

1. Create new modules in the `src` directory
2. Update the main application in `streamlit_app.py`
3. Add new dependencies to `requirements.txt`
4. Update documentation in `README.md`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- SambaNova Systems for providing the AI models
- Qdrant for the vector database
- Streamlit for the web framework
- All contributors and maintainers
