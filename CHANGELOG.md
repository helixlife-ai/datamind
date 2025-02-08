# Changelog

[English](CHANGELOG.md) | [中文](docs/CHANGELOG_zh.md)

## [0.2.1] - 2025-02-08

### Improvements
- Refactored model management system for more flexible model configuration and invocation
- Optimized environment variable configuration for improved security
- Unified API call interface with async support
- Enhanced error handling and logging
- Improved search executor's analysis capabilities and result processing

### Technical Details
- Added ModelManager class for unified local and API model management
- Added support for loading API keys and configs from environment variables
- Optimized model download and caching mechanism
- Refactored DeepSeek API integration
- Added detailed configuration documentation and examples
- Enhanced search executor features:
  * Added content fingerprint deduplication
  * Implemented deep analysis and insight generation
  * Added multi-format result export (JSON, HTML, Markdown)
  * Added timeline analysis and relationship discovery
  * Improved result formatting and summary generation

### Security
- Removed hardcoded API keys from codebase
- Added environment variable configuration examples
- Improved sensitive information handling
- Added content processing security checks

### Performance
- Implemented intelligent search result caching
- Optimized large-scale data processing efficiency
- Improved parallel content analysis
- Enhanced result deduplication and similarity calculation

## [0.2.0] - 2025-02-07

### Added
- Implemented basic search execution engine
- Added support for hybrid structured and vector queries
- Added search result formatting functionality
- Added CSV export support for search results
- Implemented detailed logging

### Features
- Added similarity threshold filtering for vector search results
- Added search result statistics
- Added automatic file naming for CSV exports
- Added structured result display with file name, type, and content
- Added custom work directory configuration

### Technical Details
- Used Python DataFrame for data processing
- Implemented exception handling mechanism
- Added UTF-8 encoding support for CSV exports
- Implemented modular code structure

## [0.1.0] - 2025-02-05

### Added
- Implemented basic search execution engine
- Added support for hybrid structured and vector queries
- Added search result formatting functionality
- Implemented detailed logging 