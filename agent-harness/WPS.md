# WPS CLI SOP

Software-specific operations guide for the WPS API CLI harness.

## Overview

The WPS API is a headless PDF conversion service built on WPS Office for Linux. This CLI provides command-line access to all API operations.

**Service URL**: Default `http://127.0.0.1:18000`

**Document Families**:
- `writer`: .doc, .docx
- `spreadsheet`: .xls, .xlsx
- `presentation`: .ppt, .pptx

## API Operations Mapping

| CLI Command | API Endpoint | Description |
|-------------|--------------|-------------|
| `wps health` | GET /api/v1/healthz | Liveness probe |
| `wps ready` | GET /api/v1/readyz | Readiness probe with checks |
| `wps convert single <file>` | POST /api/v1/convert-to-pdf | Single file conversion |
| `wps convert batch <files...>` | POST /api/v1/convert-to-pdf/batch | Batch conversion to ZIP |
| `wps config show` | - | Display current configuration |
| `wps config set <key> <value>` | - | Update configuration |

## Configuration

Configuration is stored in `~/.config/wps/config.json`.

If an existing `~/.config/cli-anything-wps/` directory is present, the CLI migrates
its config and session files into the new location automatically.

```json
{
  "api_url": "http://127.0.0.1:18000",
  "timeout": 120,
  "default_output_dir": "."
}
```

Environment variables override config file:
- `WPS_API_URL`: Service base URL
- `WPS_TIMEOUT`: Request timeout in seconds

## Common Workflows

### Check Service Status

```bash
# Quick health check
wps health

# Detailed readiness check
wps ready

# JSON output for scripting
wps ready --json
```

### Convert Single Document

```bash
# Basic conversion (outputs to same directory)
wps convert single document.docx

# Specify output path
wps convert single document.docx --output /path/to/output.pdf

# JSON output with metadata
wps convert single document.docx --json
```

### Batch Conversion

```bash
# Convert multiple files
wps convert batch file1.docx file2.pptx file3.xlsx

# Specify output ZIP path
wps convert batch *.docx --output batch_output.zip
```

### REPL Mode

```bash
# Start interactive shell
wps repl

wps> health
wps> convert single document.docx
wps> convert batch *.docx
wps> exit
```

## Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `UNSUPPORTED_FORMAT` | File extension not supported | Use .doc, .docx, .ppt, .pptx, .xls, .xlsx |
| `FAMILY_DISABLED` | Document family not enabled | Check service configuration |
| `PAYLOAD_TOO_LARGE` | File exceeds size limit | Reduce file size or increase limit |
| `CONVERSION_TIMEOUT` | Conversion took too long | Increase timeout or check WPS runtime |
| `SERVICE_UNAVAILABLE` | Service not ready | Check `wps ready` output |

## Document Family Detection

| Extension | Family | Default Enabled |
|-----------|--------|-----------------|
| .doc | writer | Yes |
| .docx | writer | Yes |
| .xls | spreadsheet | No |
| .xlsx | spreadsheet | No |
| .ppt | presentation | No |
| .pptx | presentation | No |

Enable additional families via service environment variables:
- `ENABLE_EXCEL=true`
- `ENABLE_PPT=true`
