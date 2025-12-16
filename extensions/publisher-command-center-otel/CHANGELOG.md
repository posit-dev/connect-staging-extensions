# Changelog

All notable changes to the Publisher Command Center (with OTel Tracing) extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Updated OpenTelemetry resource attributes to use well-known attribute names
  - `CONNECT_CONTENT_JOB_KEY` is now exported as `job.key`
  - `CONNECT_CONTENT_GUID` is now exported as `content.guid`
  - Other `CONNECT_*` environment variables continue to be exported with `connect.*` prefix

## [1.0.0]

### Added
- Initial release of the Publisher Command Center with OpenTelemetry tracing support.
