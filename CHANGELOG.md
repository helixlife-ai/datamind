# Changelog

[English](CHANGELOG.md) | [中文](docs/CHANGELOG_zh.md)

## [0.2.2] - 2025-02-10

### Added
- Implemented intelligent search pipeline with enhanced planning and execution
- Added DeliveryPlanner for automated content delivery planning
- Added DeliveryGenerator for intelligent content generation
- Introduced flexible result processing and delivery system
- Added customizable delivery plan templates

### Improvements
- Enhanced query intent parsing and understanding
- Improved document structure analysis and insights generation
- Advanced content organization and structuring capabilities
- Optimized result formatting and presentation
- Enhanced system stability and resource management

### Technical Details
- Added SearchPlanner for intelligent search strategy generation
- Implemented DeliveryPlanner with the following features:
  * Smart template selection and adaptation
  * Context-aware content organization
  * Multi-format output support
  * Customizable delivery rules
- Implemented DeliveryGenerator with capabilities:
  * Template-based content generation
  * Dynamic content structuring
  * Source reference management
  * Quality assurance checks
- Enhanced Executor with improved error handling and recovery
- Added support for multiple output formats
- Implemented timeline-based content organization
- Added automated report generation capabilities
- Enhanced result saving mechanisms with multiple format support
- Improved system logging and monitoring

### Performance
- Optimized cache utilization
- Improved resource management
- Enhanced error recovery mechanisms
- Better handling of large-scale data processing
- Optimized delivery plan generation speed

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

### Improvements
- Enhanced query intent parsing and understanding
- Improved document structure analysis and insights generation
- Advanced content organization and structuring capabilities
- Optimized result formatting and presentation
- Enhanced system stability and resource management

### Technical Details
- Added SearchPlanner for intelligent search strategy generation
- Implemented DeliveryPlanner with the following features:
  * Smart template selection and adaptation
  * Context-aware content organization
  * Multi-format output support
  * Customizable delivery rules
- Implemented DeliveryGenerator with capabilities:
  * Template-based content generation
  * Dynamic content structuring
  * Source reference management
  * Quality assurance checks
- Enhanced Executor with improved error handling and recovery
- Added support for multiple output formats
- Implemented timeline-based content organization
- Added automated report generation capabilities
- Enhanced result saving mechanisms with multiple format support
- Improved system logging and monitoring

### Performance
- Optimized cache utilization
- Improved resource management
- Enhanced error recovery mechanisms
- Better handling of large-scale data processing
- Optimized delivery plan generation speed 