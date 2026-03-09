# WPS API

`WPS API` 是一个基于 `WPS Office for Linux + pywpsrpc + FastAPI` 的无头 PDF 转换服务。

它专注做一件事：

- 接收 Office 文档
- 调用 WPS 导出 PDF
- 返回单个 PDF 或批量 ZIP

## 功能

当前支持这些能力：

- `doc` / `docx` 转 PDF
- `ppt` / `pptx` 转 PDF
- `xls` / `xlsx` 转 PDF
- 单文件转换
- 多文件批量转换
- 批量分发到多个 worker 提高吞吐
- 健康检查与运行环境检查

## API

### `GET /api/v1/healthz`

进程存活检查。

响应示例：

```json
{"ok": true}
```

### `GET /api/v1/readyz`

运行环境检查。

当前会检查：

- `jobs` 目录可写
- `runtime` 目录可写
- `DISPLAY` 已配置
- `XDG_RUNTIME_DIR` 已配置
- `pywpsrpc` 可导入

### `POST /api/v1/convert-to-pdf`

上传单个文件并返回 PDF。

```bash
curl -X POST \
  -F "file=@./example.docx" \
  http://127.0.0.1:8000/api/v1/convert-to-pdf \
  --output output.pdf
```

### `POST /api/v1/convert-to-pdf/batch`

上传多个文件并返回 ZIP。

```bash
curl -X POST \
  -F "files=@./a.docx" \
  -F "files=@./b.pptx" \
  -F "files=@./c.xlsx" \
  http://127.0.0.1:8000/api/v1/convert-to-pdf/batch \
  --output outputs.zip
```

## 支持格式

- Writer: `.doc`, `.docx`
- Presentation: `.ppt`, `.pptx`
- Spreadsheet: `.xls`, `.xlsx`

## 目录结构

```text
.
├── app/
│   ├── adapters/
│   ├── api/
│   ├── services/
│   └── utils/
├── docker/
│   ├── conf/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── *.sh
├── scripts/
├── requirements.txt
└── README.md
```

## 运行方式

### 构建镜像

最简单的方式：

```bash
docker build -f docker/Dockerfile -t quantatrisk/wps-api:local .
```

也可以使用交互式脚本：

```bash
./scripts/build_image.sh
```

`docker/Dockerfile` 会：

- 下载 WPS Linux 安装包
- 下载 `https://software.cdn.vect.one/Fonts.zip`
- 把中文字体打进镜像

如果你要替换下载源，可以覆盖下面两个构建参数：

```bash
docker build \
  -f docker/Dockerfile \
  --build-arg WPS_DEB_URL_BASE=https://your-mirror.example.com/wps-office.deb \
  --build-arg FONTS_ZIP_URL=https://your-cdn.example.com/Fonts.zip \
  -t quantatrisk/wps-api:local .
```

### 运行单容器

```bash
docker run --rm \
  -p 8000:8000 \
  -v $(pwd)/workspace:/workspace \
  quantatrisk/wps-api:local
```

### 启动集群

标准启动方式只有一种：

```bash
./scripts/build_image.sh
WPS_WORKER_COUNT=8 ./scripts/compose_up.sh
```

不要直接执行 `docker compose up`。

因为 `docker/docker-compose.yml` 只定义 service，不会按 `WPS_WORKER_COUNT` 自动扩容 worker；直接执行时通常只会启动：

- 1 个 `wps-api`
- 1 个 `wps-worker`
- 1 个 `wps-worker-lb`

### 默认行为

- `wps-api`: 对外 dispatcher，默认暴露到 `18000`
- `wps-worker`: 可横向扩容的实际转换节点
- `wps-worker-lb`: 内部轻量负载均衡，仅给 dispatcher 使用

### 常用环境变量

- `WPS_WORKER_COUNT`: worker 数量，默认 `8`
- `WPS_API_PORT`: 对外端口，默认 `18000`
- `WPS_DISPATCHER_REQUEST_TIMEOUT_SECONDS`: dispatcher 到 worker 超时，默认 `180`
- `WPS_BATCH_MAX_FILES`: batch 最大文件数，默认 `10`
- `WPS_IMAGE`: compose 使用的镜像名，默认 `quantatrisk/wps-api:latest`

停止并清理：

```bash
docker compose -f docker/docker-compose.yml down --remove-orphans
```

## 本地调试

如果本机已经具备完整 Linux WPS 运行时，可以直接启动 API：

```bash
./scripts/run_local_api.sh
```

快速烟测：

```bash
./scripts/smoke_test_api.sh
./scripts/smoke_test_api.sh tests/files/经责审计报告示例.docx
```

## 环境变量

- `WPS_WORKSPACE_ROOT`: 工作目录根路径，默认 `/workspace`
- `WPS_CONVERSION_TIMEOUT_SECONDS`: 转换超时秒数，默认 `120`
- `WPS_CLEANUP_MAX_AGE_SECONDS`: 历史任务清理阈值，默认 `86400`
- `WPS_MAX_UPLOAD_SIZE_BYTES`: 上传大小上限，默认 `52428800`
- `WPS_BATCH_MAX_FILES`: 批量文件数上限，默认 `10`
- `WPS_BATCH_WORKER_URLS`: worker 基础地址列表；配置后批量接口会启用远程分发
- `WPS_DISPATCHER_REQUEST_TIMEOUT_SECONDS`: dispatcher 调 worker 的超时秒数，默认 `180`

## 边界

- 单实例内同文档族串行执行，避免 WPS 自动化互相干扰
- 批量接口是受控并发，不保证部分成功返回
- 当前没有鉴权、队列、重试中心和任务持久化
