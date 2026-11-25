# Changelog

[한국어](docs/kor/CHANGELOG.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Load built-in model capabilities lazily with safe basic-call fallback, validate operator rules strictly, and support inheriting built-in identities. Unsupported explicit reasoning still fails before transport. See [usage](docs/llm-inference.md#model-capabilities-and-operator-extensions).

- Separate usage recording from optional cost calculation; support four-line operator prices, cache reads and input bands. Accounting failures preserve parsing results, and records without snapshots can be repriced. See [setup](docs/llm-inference.md).

- Native YAML DAG configuration with typed DTOs, strict compilation, page-level
  scheduling, configurable concurrency, and document assembly.
- PDF text extraction, Dolphin layout integration, PaddleOCR, table/image VLM
  interpretation, Markdown output, images, and structured table formats.
- Local Dolphin 1.5/Paddle tutorials, router service, configuration editor,
  optional Langfuse usage export, and a separate Confluence upload pipeline.
- English/Korean contribution, security, conduct, data-handling, release,
  model/data asset, third-party, and evaluation documentation; Issue/PR templates.

### Changed

- Global Context accepts strict nonnegative `skip_levels`, defaulting to `[]`.
  Default, managed_endpoints and group_internal set `[1]` to retain Stage 1 L1
  content without an additional render or VLM request. Existing errors, page
  order, tables, image links, structured blocks and debug content are preserved.
  Set `[]` to restore all-page refinement; light whole-page calls still run
  when needed.

### Fixed

- Whole-page VLM responses use an explicit body schema so JSON envelopes do not
  enter final Markdown. Native text extraction and L1 Global Context skipping remain.
- OpenAI chat requests omit `temperature` unless explicitly configured.
- Streams missing a terminal reason retry within the existing attempt/time limits;
  partial output is never accepted as a completed page.
- Failed Global Context refinement retains successful upstream content and tables
  while recording the failure. Dolphin failures have private diagnostic artifacts.
- Repeated table references in a model note and output no longer create false
  structured-restoration failures.
- Default, managed_endpoints and group_internal use `PADDLE_SSL`, defaulting to
  `true`; HTTP Paddle servers can set it to `false`.

### Security

- Configurable HTTP body/image/pixel/batch/prompt limits, request queue limits,
  body read timeouts, and bounded YAML expansion for local helper services.
- Dependency version pins and secret-scan workflow configuration.

### Documentation

- Apache-2.0 parser license and organization CLA links.
- Apache-2.0 license and copyright notices for all three bundled EfficientNet B0
  router checkpoints, permitting commercial use, modification, and redistribution.
- PP-DocLayoutV3 (Apache 2.0) recommendation for commercial use; Dolphin v2
  research-license conditions and separate benchmark configuration descriptions.

### Known limitations

- PP-DocLayoutV3 requires a compatible layout adapter and is not in the supplied
  profiles or reported benchmark scores.
- Managed/group-service full runs, real Langfuse delivery, and Confluence update/
  attachment replacement have separate validation requirements.
- Sample and evaluation asset rights require separate records; inclusion in
  this repository does not extend the parser license to third-party materials.
