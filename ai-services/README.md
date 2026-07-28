# 🤖 AI Services — AI-Based Chartered Accountant

## Overview

AI and machine learning services powering intelligent features. Includes OCR document scanning, multilingual translation, AI chatbot, government updates scraping, document classification, risk analysis, and knowledge base with vector embeddings.

## Directory Structure

```
ai-services/
├── ocr/
│   ├── invoice_reader/       → Invoice data extraction (Tesseract + EasyOCR)
│   └── document_scanner/     → General document OCR scanning
├── translation/
│   ├── language_detector/    → Automatic language detection
│   └── translator/           → Multi-language translation (Google Translate)
├── chatbot/
│   ├── prompt_templates/     → LLM prompt engineering templates
│   └── conversation/         → Conversation management & history
├── rule-engine/              → Business rule validation engine
├── scrapers/
│   ├── parsers/              → HTML/PDF content parsers
│   └── summarizer/           → Content summarization (Gemini)
├── classifier/               → Document & query classification
├── impact-analysis/          → Regulatory impact analysis
├── recommendation_engine/    → Financial recommendations
├── risk_analysis/            → Risk assessment engine
└── knowledge_base/
    ├── embeddings/           → Text embedding generation
    └── vector_store/         → Vector database for RAG
```

## Technologies

| Feature           | Technology              |
|-------------------|-------------------------|
| LLM               | Google Gemini via LangChain |
| OCR               | Tesseract + EasyOCR     |
| Translation       | Google Cloud Translate  |
| Web Scraping      | BeautifulSoup + Playwright |
| Embeddings        | Gemini Embeddings       |

## Developer Guidelines

- Each AI service should be independently testable
- Use dependency injection for API keys and configuration
- Cache expensive AI API calls when possible
- Log all AI interactions for debugging and improvement
- Follow prompt engineering best practices
