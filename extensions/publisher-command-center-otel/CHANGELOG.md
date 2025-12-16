# Changelog

All notable changes to the Publisher Command Center (with OTel Tracing) extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added startup instrumentation to track application initialization performance
  - `startup.imports` - tracks time to import third-party libraries
  - `startup.initialization` - tracks Connect client, FastAPI app, and cache creation

### Removed
- Removed unused `from http import client` import

### Changed
- Updated OpenTelemetry resource attributes to use well-known attribute names
  - `CONNECT_CONTENT_JOB_KEY` is now exported as `job.key`
  - `CONNECT_CONTENT_GUID` is now exported as `content.guid`
  - Only explicitly safe environment variables are exported (no automatic collection of all `CONNECT_*` variables)

## [1.0.0]

### Added
- Initial release of the Publisher Command Center with OpenTelemetry tracing support.
