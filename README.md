# WPS API Service

这是一个基于 `WPS Office for Linux + pywpsrpc + FastAPI` 的无头文档转换服务原型。

当前已支持：

- `GET /api/v1/healthz`
- `GET /api/v1/readyz`
- `POST /api/v1/convert-to-pdf`
- `POST /api/v1/convert-to-pdf/batch`

## 项目定位

本仓库现在包含三层内容：

- `pywpsrpc/`：上游 Python 绑定源码与示例，作为能力参考与依赖来源
- `Dockerfile` + `docker/entrypoint.sh`：WPS 运行时容器基础设施
- `app/`：本项目新增的 FastAPI 服务层

推荐的职责边界是：

- `pywpsrpc` 负责 WPS RPC 调用
- `app/` 负责 API、任务目录、日志、超时、互斥锁、错误处理

## 目录说明

```text
.
├── app/
│   ├── api/
│   ├── adapters/
│   ├── services/
│   └── utils/
├── docker/
├── docs/
├── scripts/
├── Dockerfile
├── Office.conf
└── README.md
```

## 当前 API

### `GET /api/v1/healthz`

用于探测服务进程是否存活。

响应示例：

```json
{"ok": true}
```

### `GET /api/v1/readyz`

用于探测运行环境是否具备接单能力。

会检查：

- `jobs` 目录可写
- `runtime` 目录可写
- `DISPLAY` 是否配置
- `XDG_RUNTIME_DIR` 是否配置
- `pywpsrpc` 是否可导入

### `POST /api/v1/convert-to-pdf`

上传单个受支持文件，返回 PDF 文件流。

请求示例：

```bash
curl -X POST \
  -F "file=@./example.docx" \
  http://127.0.0.1:8000/api/v1/convert-to-pdf \
  --output output.pdf
```

## 构建前提

在构建镜像前，请确认根目录存在以下文件：

- `Office.conf`

当前 `Dockerfile` 会默认从 WPS Linux 官方下载页解析出的安装包地址下载 `.deb`。
如果你想固定到自己的镜像源或本地文件服务器，可以在构建时覆盖 `WPS_DEB_URL_BASE`。

## 构建镜像

交互式构建脚本：

```bash
./scripts/build_image.sh
```

直接构建：

```bash
docker build -t wps-api-service:local .
```

使用自定义安装包地址：

```bash
docker build \
  --build-arg WPS_DEB_URL_BASE=https://your-mirror.example.com/wps-office.deb \
  -t wps-api-service:local .
```

## 运行容器

```bash
docker run --rm \
  -p 8000:8000 \
  -e DISPLAY=:99 \
  -e XDG_RUNTIME_DIR=/workspace/runtime \
  wps-api-service:local
```

如果想持久化任务目录，可以挂载卷：

```bash
docker run --rm \
  -p 8000:8000 \
  -v $(pwd)/workspace:/workspace \
  wps-api-service:local
```

## 快速验证

### 仅验证健康检查

```bash
curl http://127.0.0.1:8000/api/v1/healthz
curl http://127.0.0.1:8000/api/v1/readyz
```

### 验证单文件转 PDF

```bash
curl -X POST \
  -F "file=@./example.docx" \
  http://127.0.0.1:8000/api/v1/convert-to-pdf \
  --output output.pdf
```

## 本地开发说明

如果你是在一台已经准备好 WPS、Xvfb、dbus、`pywpsrpc` 的 Linux 环境中本地调试，可以直接运行：

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果只是做服务层代码调试，没有完整 WPS 环境：

- `healthz` 可验证 API 启动
- `readyz` 和真实转换会依赖运行环境

## 环境变量

支持以下环境变量：

- `WPS_WORKSPACE_ROOT`：工作目录根路径，默认 `/workspace`
- `WPS_CONVERSION_TIMEOUT_SECONDS`：转换超时秒数，默认 `120`
- `WPS_CLEANUP_MAX_AGE_SECONDS`：历史任务清理阈值，默认 `86400`
- `WPS_MAX_UPLOAD_SIZE_BYTES`：上传大小上限，默认 `52428800`
- `WPS_BATCH_MAX_FILES`：批量文件数上限，默认 `10`
- `WPS_PDF_USE_GHOSTSCRIPT`：是否执行 Ghostscript 重写，默认 `true`

## 已知限制

当前版本仍保持 KISS 边界，限制包括：

- 单实例内同文档族转换串行执行
- 还未加入 API Key 鉴权
- 还未加入异步任务队列
- 还未支持部分成功的批量返回

## 参考文档

- 研究分析：`docs/wps-server-research.md`
- 开发方案：`docs/api-service-development-plan.md`
