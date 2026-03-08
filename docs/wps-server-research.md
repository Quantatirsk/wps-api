# WPS Server 项目能力研究与 API 化改造建议

## 1. 项目现状概览

这个仓库当前只有两部分核心内容：

- 根目录 `Dockerfile`：把 Ubuntu 22.04、WPS Office for Linux、`pywpsrpc`、`Xvfb`、`dbus` 组装到一个容器里，让 WPS 可以在“无头服务器”环境中启动。
- `pywpsrpc/`：WPS Office RPC 的 Python 绑定源码与示例代码。它不是一个 HTTP 服务，而是一层“WPS 自动化控制接口”。

换句话说，这个项目现在**已经证明了“服务器侧启动 WPS 并通过 Python 控制它”是可行的**，但它还**不是**一个可直接给任意客户端调用的 API 服务。

当前容器做的事情，本质上是：

1. 伪造一个 Linux 桌面运行环境：`Xvfb + dbus + Qt`。
2. 启动 WPS 文字 / 演示 / 表格进程。
3. 通过 `pywpsrpc` 调用其 RPC / COM 风格对象模型。
4. 在 Python 中执行“打开文档、编辑、另存为、导出 PDF”等操作。

因此，这个仓库天然适合被改造成：

- 文档转换服务
- 文档自动化处理服务
- 远程 Office 能力服务
- 内部微服务（供 SaaS、企业系统、工作流引擎调用）

## 2. 这个项目已经具备的具体能力

下面的能力并不是“理论上可能”，而是能从仓库里的 `README`、示例、测试代码里直接看出来的。

### 2.1 WPS 文字（Writer / `rpcwpsapi`）

从 `pywpsrpc/README.md`、`pywpsrpc/examples/rpcwpsapi/convertto/convertto.py`、`pywpsrpc/tests/test_rpcwpsapi.py` 可以确认，WPS 文字至少可以做到：

- 启动 WPS Writer 进程。
- 打开已有文档。
- 创建空白文档。
- 读取 / 插入 / 修改文本。
- 操作光标与选区。
- 段落级格式控制。
- 字体格式控制，例如加粗。
- 查找文本。
- 插入表格。
- 插入图形。
- 保存文档、另存为其他格式。
- 导出为 PDF。
- 注册事件回调，例如保存前、关闭前、文档打开后。

结合示例代码，当前仓库**已明确验证**的 Writer 输出格式包括：

- `doc`
- `docx`
- `rtf`
- `html`
- `pdf`
- `xml`

这意味着：

- `docx -> pdf`
- `doc -> pdf`
- `docx -> html`
- `docx -> doc`
- `doc -> docx`

这类能力都可以围绕现有示例改造成 API。

### 2.2 WPS 演示（Presentation / `rpcwppapi`）

从 `pywpsrpc/examples/rpcwppapi/wpp_convert.py` 以及事件测试可以确认：

- 可以启动 WPS 演示进程。
- 可以打开演示文稿。
- 可以在无窗口模式下打开文稿（示例使用 `WithWindow=False`）。
- 可以导出为 PDF。
- 可以接收演示相关事件，例如打开、保存、关闭等。

当前仓库中“明确落地示例”的能力主要是：

- `ppt -> pdf`
- `pptx -> pdf`

### 2.3 WPS 表格（Spreadsheet / `rpcetapi`）

从 `pywpsrpc/examples/rpcetapi/et_convert.py` 与测试代码可以确认：

- 可以启动 WPS 表格进程。
- 可以打开工作簿。
- 可以创建工作簿。
- 可以导出为 PDF。
- 可以注册事件。

当前仓库中“明确落地示例”的能力主要是：

- `xls -> pdf`
- `xlsx -> pdf`

### 2.4 事件驱动能力

从 `pywpsrpc/tests/test_rpcevents.py` 可以看到，它不只是“静态转换”，还支持事件监听，例如：

- 文档保存前
- 文档关闭前
- 文档打开后
- 新建文档
- 应用退出
- 演示保存 / 关闭
- 表格相关事件

这类能力适合未来扩展成：

- 审计日志
- 自动水印
- 自动校验
- 保存前处理钩子
- 工作流触发器

### 2.5 进程级管理能力

从示例代码里还能看到：

- 可获取 WPS 子进程 PID。
- 可显式调用 `Quit()`。
- 部分示例中会在结束后直接 `kill -9` 清理子进程。

这说明这个项目不仅能“调用 WPS”，还可以围绕 WPS 做**服务端进程生命周期管理**。这对 API 服务非常关键，因为转换服务最怕文档处理完成后残留僵尸进程。

## 3. 这个项目的本质边界

这个项目适合做“远程文档能力服务”，但需要明确几个边界。

### 3.1 它不是纯命令行转换器

WPS for Linux 本身依赖图形环境，因此当前方案并不是真正意义上的“纯 headless 二进制”。它是通过：

- `Xvfb`
- `dbus`
- Qt 运行环境
- `QT_QPA_PLATFORM=offscreen`

把“桌面应用”伪装成服务器可运行进程。

所以这个项目的正确理解是：

> 在 Ubuntu Server 中，通过虚拟显示与 RPC 自动化，把 WPS 包装成无头服务。

### 3.2 它适合做异步任务服务，不适合直接高并发并行轰炸

WPS 本体是桌面应用，不是为高并发多租户场景原生设计的。即使容器化了，也不建议在同一个 WPS 进程内同时处理很多任务。

更合理的服务模型是：

- 单 worker 串行处理；或
- 少量 worker 池，每个 worker 独占自己的 WPS 进程；或
- 按文档类型拆分服务：Writer / Presentation / Spreadsheet 分开部署。

如果直接把 FastAPI 接成“一个接口收到几十个请求就并发开几十个转换”，稳定性通常不会好。

### 3.3 商业授权与文件兼容性要单独评估

`pywpsrpc` 采用 MIT，但实际运行依赖的 WPS Office for Linux 是否允许你的业务形态商用，需要单独确认。

此外，不同 WPS 版本、字体环境、语言包，都会影响：

- 排版一致性
- 导出 PDF 的分页
- 字体替换
- 页眉页脚、批注、目录、公式等复杂元素的兼容性

所以这个服务上线前应做一轮“样本文档兼容性基线测试”。

## 4. 对现有 Dockerfile 的判断

当前根目录 `Dockerfile` 已经证明了思路可行，但它更像“验证容器里能跑起来”，距离“生产可用 API 服务镜像”还有明显差距。

### 4.1 当前 Dockerfile 的优点

- 已安装 WPS 运行所需的大量图形 / Qt 依赖。
- 已处理 `Xvfb`、`dbus`、`DISPLAY` 等关键环境。
- 已预置 `Office.conf`，跳过 EULA 与部分首次启动配置。
- 已安装 `pywpsrpc`。
- 已把容器默认命令设置为简单导入测试。

说明开发者已经摸到了关键门槛：**WPS 能在容器里起、RPC 能连上**。

### 4.2 当前 Dockerfile 的主要问题

#### 问题 1：它没有 API 进程

当前 `CMD` 只是：

```bash
python3 -c "from pywpsrpc.rpcwpsapi import createWpsRpcInstance; print('pywpsrpc 导入成功')"
```

这只能验证环境，不能对外提供服务。

#### 问题 2：入口脚本偏“临时拼装”

当前 `/entrypoint.sh` 通过 `echo` 生成，能用，但不够稳健：

- 没有 `set -euo pipefail`
- 没有信号转发与子进程回收
- 没有健康检查逻辑
- 没有对 `dbus`、`XDG_RUNTIME_DIR` 做权限和目录完整性处理

对于长期运行的 API 服务，这会增加“偶发性挂死 / 僵尸进程 / 退出不彻底”的风险。

#### 问题 3：没有任务隔离目录

当前镜像没有约定：

- 上传文件放哪
- 转换输出放哪
- 临时目录怎么清理
- 多个请求如何隔离

如果你把它做成 API 服务，必须显式约定：

- `/workspace/inbox`
- `/workspace/outbox`
- `/workspace/tmp`

否则多请求会互相污染。

#### 问题 4：没有并发控制

当前容器没有任何“WPS 实例互斥 / 串行队列 / worker 池”设计。对 API 服务来说，这是最重要的工程问题之一。

#### 问题 5：缺少服务健康探针

没有：

- HTTP `healthz`
- 启动就绪探针
- WPS 自检逻辑

生产中容器虽然“进程活着”，但未必“还能正常转换文件”。

#### 问题 6：镜像可维护性一般

例如：

- 依赖安装里有重复包名。
- `pip install` 没有版本锁定。
- WPS `.deb` 被直接 `COPY` 进去，升级流程不清晰。
- `libtiff.so.6 -> libtiff.so.5` 的软链接属于兼容性补丁，建议在文档中显式记录风险。

#### 问题 7：字体与本地化还不够完整

如果目标是处理中文 / 英文 / Office 常见模板，通常至少还要考虑：

- CJK 字体
- 微软常用字体兼容替代
- 区域语言 / locale
- 时区与字体缓存

否则 Word 转 PDF 很容易出现“能转，但版式不对”。

## 5. 把它改造成 API 服务的推荐方案

## 5.1 总体架构建议

推荐把当前项目改造成下面这种结构：

```text
.
├── Dockerfile
├── docker/
│   └── entrypoint.sh
├── app/
│   ├── main.py
│   ├── schemas.py
│   ├── services/
│   │   ├── conversion.py
│   │   ├── writer.py
│   │   ├── presentation.py
│   │   └── spreadsheet.py
│   └── utils/
│       ├── files.py
│       └── locks.py
└── docs/
    └── wps-server-research.md
```

职责拆分如下：

- `Dockerfile`：只负责构建运行环境。
- `entrypoint.sh`：负责拉起 `Xvfb`、`dbus`、运行 API。
- `app/main.py`：FastAPI / Flask 入口。
- `services/*.py`：封装 `pywpsrpc` 调用。
- `utils/locks.py`：做文档类型级别的互斥锁或 worker 锁。

## 5.2 推荐暴露的 API 能力

第一阶段建议不要做“万能 Office 平台”，先聚焦高价值、低复杂度接口：

- `POST /api/v1/convert-to-pdf`
- `POST /api/v1/convert/ppt-to-pdf`
- `POST /api/v1/convert/excel-to-pdf`
- `GET /api/v1/healthz`
- `GET /api/v1/readyz`

如果想再抽象一点，可以统一成：

- `POST /api/v1/convert`

请求参数：

- 上传文件
- `source_type`，例如 `docx`
- `target_type`，例如 `pdf`

但从落地角度，我更推荐先做“显式端点”，因为：

- 更容易做权限控制
- 更容易限制支持格式
- 更容易做故障排查
- 更容易按类型分配不同 worker

## 5.3 `word -> pdf` 的最小 API 设计

### 请求

`multipart/form-data`

- `file`: Word 文件，例如 `.doc` / `.docx`

### 响应

- 成功：直接返回 PDF 文件流
- 失败：返回 JSON 错误信息

### 处理流程

1. API 接收上传文件。
2. 生成任务目录，例如 `/workspace/jobs/<uuid>/`。
3. 保存原始文件到 `input.docx`。
4. 进入 Writer 服务逻辑。
5. 获取 Writer 互斥锁。
6. 通过 `pywpsrpc` 打开文档。
7. Writer 优先调用 `SaveAs2(..., wdFormatPDF)`；Presentation / Spreadsheet 继续使用各自的固定格式导出。
8. 关闭文档、退出应用或归还 worker。
9. 返回生成的 PDF。
10. 清理任务临时目录。

## 5.4 为什么要做互斥锁 / 队列

推荐至少在 Writer 转换上加一个进程内锁：

- 同一时刻只允许一个 Writer 转换任务进入同一个 WPS 实例。

原因不是 FastAPI 不支持并发，而是 WPS 桌面应用本身并不适合被高并发共享调用。

最简单可靠的方式是：

- 一个容器只跑一个 API 进程。
- API 内部对每类应用加一把 `asyncio.Lock` 或文件锁。

更进一步的方式是：

- 一个 Writer 容器
- 一个 WPP 容器
- 一个 ET 容器

分别水平扩容。

## 6. Dockerfile 应该如何改造

下面不是唯一方案，但这是比较适合“加自定义代码并提供 API”的方向。

### 6.1 改造目标

新的镜像应该同时满足：

- 能运行 WPS
- 能运行 Python API 服务
- 能稳定启动 `Xvfb + dbus`
- 有明确工作目录
- 有健康检查
- 便于后续扩展自定义代码

### 6.2 推荐 Dockerfile 结构

下面是一份更接近“服务镜像”的参考写法：

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QT_QPA_PLATFORM=offscreen \
    DISPLAY=:99 \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

WORKDIR /app

RUN sed -i 's@//.*archive.ubuntu.com@//mirrors.ustc.edu.cn@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    curl \
    wget \
    xvfb \
    dbus-x11 \
    xdg-utils \
    python3 \
    python3-pip \
    python3-venv \
    libxslt1.1 \
    libx11-6 \
    libxext6 \
    libxtst6 \
    libxi6 \
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5 \
    libqt5x11extras5 \
    libqt5network5 \
    libglib2.0-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libgl1-mesa-glx \
    libglu1-mesa \
    libxrender1 \
    libxcursor1 \
    libxcomposite1 \
    libasound2 \
    libfontconfig1 \
    libnss3 \
    libgbm1 \
    fonts-opensymbol \
    fonts-noto-cjk \
    locales && \
    locale-gen zh_CN.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 /usr/lib/x86_64-linux-gnu/libtiff.so.5

COPY wps-office_12.1.2.23578_amd64.deb /tmp/wps.deb
RUN apt-get update && apt-get install -y /tmp/wps.deb && \
    rm -f /tmp/wps.deb && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install \
    pywpsrpc \
    fastapi \
    uvicorn[standard] \
    python-multipart

RUN mkdir -p /root/.config/Kingsoft
COPY Office.conf /root/.config/Kingsoft/Office.conf

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY app /app/app

RUN mkdir -p /workspace/jobs /workspace/runtime

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

这份改造的重点是：

- 加入 API 运行时依赖。
- 预留 `app/` 自定义代码目录。
- 增加健康检查。
- 增加工作目录。
- 补充字体与 locale。
- 默认启动 HTTP 服务，而不是只做导入测试。

## 6.3 推荐的 `entrypoint.sh`

建议把入口脚本从 Dockerfile 里的 `echo` 改成独立文件，类似：

```bash
#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=${DISPLAY:-:99}
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/workspace/runtime}

mkdir -p "$XDG_RUNTIME_DIR" /var/run/dbus
chmod 700 "$XDG_RUNTIME_DIR"

dbus-uuidgen --ensure=/etc/machine-id

Xvfb "$DISPLAY" -screen 0 1280x1024x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

eval "$(dbus-launch --sh-syntax)"

cleanup() {
  kill "$XVFB_PID" 2>/dev/null || true
  if [[ -n "${DBUS_SESSION_BUS_PID:-}" ]]; then
    kill "$DBUS_SESSION_BUS_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT TERM INT

exec "$@"
```

这个版本比当前脚本更适合长期运行服务，因为它至少做了：

- 严格错误退出
- 资源目录初始化
- 信号捕获与清理
- `Xvfb` / `dbus` 子进程回收

## 7. 自定义代码应该加在哪里

如果你的目标是“让任意客户端调用接口完成 Word 转 PDF”，建议新增 `app/` 目录，把业务逻辑和容器逻辑拆开。

推荐最小实现：

- `app/main.py`：API 路由
- `app/services/writer.py`：Word 转 PDF
- `app/utils/files.py`：任务目录与清理
- `app/utils/locks.py`：互斥锁

### 7.1 `app/main.py` 示例

```python
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.services.writer import convert_word_to_pdf

app = FastAPI(title="WPS Server API")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/v1/convert-to-pdf")
async def word_to_pdf(file: UploadFile = File(...)):
    filename = file.filename or "input.docx"
    if not filename.lower().endswith((".doc", ".docx")):
        raise HTTPException(status_code=400, detail="only .doc/.docx supported")

    pdf_path = await convert_word_to_pdf(file)
    return FileResponse(pdf_path, media_type="application/pdf", filename="output.pdf")
```

### 7.2 `app/services/writer.py` 示例

下面的示例展示的是“服务化封装思路”，核心点是：

- 保存上传文件
- 串行调用 WPS
- 打开文档
- 导出 PDF
- 清理资源

```python
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from pywpsrpc.common import QtApp, S_OK
from pywpsrpc.rpcwpsapi import createWpsRpcInstance, wpsapi

writer_lock = asyncio.Lock()


def _convert_sync(src: str, dst: str):
    qapp = QtApp([])

    hr, rpc = createWpsRpcInstance()
    if hr != S_OK:
        raise RuntimeError(f"createWpsRpcInstance failed: {hr}")

    hr, app = rpc.getWpsApplication()
    if hr != S_OK:
        raise RuntimeError(f"getWpsApplication failed: {hr}")

    app.Visible = False

    hr, doc = app.Documents.Open(src, ReadOnly=True)
    if hr != S_OK:
        app.Quit(wpsapi.wdDoNotSaveChanges)
        raise RuntimeError(f"Documents.Open failed: {hr}")

    try:
        result = doc.SaveAs2(dst, FileFormat=wpsapi.wdFormatPDF)
        if result != S_OK:
            raise RuntimeError(f"SaveAs2 PDF failed: {result}")
    finally:
        doc.Close(wpsapi.wdDoNotSaveChanges)
        app.Quit(wpsapi.wdDoNotSaveChanges)


async def convert_word_to_pdf(upload_file):
    suffix = Path(upload_file.filename or "input.docx").suffix or ".docx"
    job_dir = Path(tempfile.mkdtemp(prefix="wps-job-", dir="/workspace/jobs"))
    src_path = job_dir / f"input{suffix}"
    dst_path = job_dir / "output.pdf"

    try:
        with src_path.open("wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        async with writer_lock:
            await asyncio.to_thread(_convert_sync, str(src_path), str(dst_path))

        if not dst_path.exists():
            raise RuntimeError("output pdf not generated")

        return str(dst_path)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
```

这个实现还比较朴素，但已经足够作为第一版 API 服务骨架。

## 8. 为什么这套方案可以支持“任意客户端”

这里的“任意客户端”不应该理解为“客户端里必须装 WPS”，而应理解为：

- 任意能发 HTTP 请求的客户端

例如：

- Web 前端
- Java / Go / Python / Node.js 后端
- iOS / Android App
- 企业微信 / 钉钉 / 飞书机器人
- 低代码平台 / 工作流引擎

因为一旦你把 WPS 能力封装成 HTTP 上传下载接口，客户端只需要：

1. 上传 Word 文件。
2. 等待返回 PDF。

客户端不再关心：

- WPS 是否安装
- Linux 是否有桌面环境
- RPC 如何初始化
- `Xvfb`、`dbus` 如何启动

这些复杂性全部被容器封装了。

## 9. 第一阶段最值得做的 API 列表

如果只做最小可用版本，我建议优先级如下：

### P0

- `GET /api/v1/healthz`
- `POST /api/v1/convert-to-pdf`

这是最容易变成真实业务价值的能力。

### P1

- `POST /api/v1/convert/ppt-to-pdf`
- `POST /api/v1/convert/excel-to-pdf`

这两项已有示例支撑，扩起来很自然。

### P2

- `POST /v1/convert/word-to-html`
- `POST /v1/convert/doc-to-docx`
- `POST /api/v1/inspect/formats`

这是基于 Writer 多格式导出能力往前走一步。

### P3

- 任务异步化
- 回调通知
- 对象存储集成（S3 / MinIO / OSS）
- 鉴权（API Key / JWT）
- 审计日志

这些更像“服务产品化”的第二阶段。

## 10. 上线前必须补的工程项

如果你真的要把它作为服务给别的系统用，除了代码跑通，还应至少补齐这些事项：

- 请求大小限制，避免超大文档打爆容器。
- 单任务超时控制，避免 WPS 卡死。
- 子进程回收机制。
- 临时文件自动清理。
- 失败重试策略。
- 并发限制与排队策略。
- 统一错误码。
- 日志里打印任务 ID、输入扩展名、耗时、WPS PID。
- 字体基线测试。
- 样本文档回归测试。

如果没有这些，服务即使“功能上能跑”，也很难长期稳定。

## 11. 结论

这个项目目前已经证明了一件很重要的事：

> 通过 `Xvfb + dbus + WPS Office for Linux + pywpsrpc`，可以在 Ubuntu Server 容器中无头运行 WPS，并通过 Python 控制它完成文档自动化。

基于仓库现有内容，可以较明确地说，这个项目已经能够作为下面这些能力的基础：

- Word 文档打开、编辑、保存
- Word 多格式互转，尤其是 `Word -> PDF`
- PPT / PPTX 转 PDF
- XLS / XLSX 转 PDF
- 事件监听与自动化处理

如果你想把它真正变成“任意客户端都能调用的远程 Office 能力服务”，最合理的落地方向是：

- 保留当前容器化思路；
- 在镜像中加入 FastAPI 等自定义代码；
- 用 `app/services/*.py` 封装 `pywpsrpc`；
- 用 HTTP 上传下载接口暴露转换能力；
- 用锁 / 队列约束 WPS 并发；
- 补上健康检查、任务隔离、日志、清理机制。

其中，最值得优先落地、也最容易变成通用 API 的能力就是：

- `POST /api/v1/convert-to-pdf`

这条链路与仓库现有能力最贴近、工程收益最高、实现成本最低。

## 12. 参考位置

- 当前容器入口与运行思路：`Dockerfile`
- Python 绑定总体说明：`pywpsrpc/README.md`
- Writer 格式转换示例：`pywpsrpc/examples/rpcwpsapi/convertto/convertto.py`
- Presentation 转 PDF 示例：`pywpsrpc/examples/rpcwppapi/wpp_convert.py`
- Spreadsheet 转 PDF 示例：`pywpsrpc/examples/rpcetapi/et_convert.py`
- 事件能力示例：`pywpsrpc/tests/test_rpcevents.py`
- Writer 自动化能力示例：`pywpsrpc/tests/test_rpcwpsapi.py`


## 13. 2026-03-08 实测补充：中文字体、PDF 体积与 macOS Preview

这轮实际部署与样例验证，补充得出以下结论。

### 13.1 根因判断

`tests/files/经责审计报告示例.docx` 在 Linux 容器里直接导出 PDF 时，出现了两个叠加问题：

- **字体缺失时**，WPS 会把文档中的方正字体、宋体、楷体、黑体等替换成 `Noto Sans/Serif CJK` 一类兜底字体。
- **字体补齐后**，WPS Linux 导出的 PDF 会大量嵌入 CJK 字体子集，导致文件体积暴涨。

这也解释了用户观察到的现象：

- Chrome 打开时能显示，但字体看起来接近“统一黑体化”。
- macOS Preview 打开时存在乱码或兼容性异常。
- 在 Windows WPS 中导出的 PDF 只有一百多 KB，而 Linux 容器里一度达到 5.1M 甚至 20M。

### 13.2 已验证的修复路径

#### 第一步：把真实中文字体挂载进容器

在目标主机上把字体放到：

- `/opt/wps-api-service/zhFonts`

容器启动时挂载为：

- `/usr/local/share/fonts/zhFonts`

并在 `docker/entrypoint.sh` 中执行：

- `fc-cache -f "$WPS_FONT_DIR"`
- `fc-cache -f`

实测挂载后，WPS 已能命中这些字体：

- `方正小标宋简体`
- `方正仿宋简体`
- `SimSun`
- `SimHei`
- `KaiTi`
- `仿宋`
- `Microsoft YaHei`

导出 PDF 中也可以看到对应嵌入字体，而不再是 `Noto` 兜底。

#### 第二步：不要只停留在 WPS 原始导出，追加 Ghostscript 重写

只靠 WPS 原始导出，版式更接近原文，但文件会非常大。当前实测中：

- 原始 WPS PDF：约 `20M`

在容器内使用 Ghostscript 重新写一遍 PDF 后，体积显著下降，同时仍保留正确的中文字体映射。

本次验证结果如下：

- 原始 WPS 导出：约 `20M`
- `gs /prepress`：约 `3.7M`
- `gs /printer`：约 `2.0M`
- 自定义 `150dpi`：约 `1.6M`
- `gs /ebook`：约 `838K`
- 自定义 `96dpi`：约 `980K`
- `gs /screen`：约 `686K`

结合版式与清晰度权衡，当前服务默认采用**自定义下采样参数**，而不是直接套 `/screen`：

- 彩色图片：`96dpi`
- 灰度图片：`96dpi`
- 单色图片：`200dpi`
- 保持 `SubsetFonts=true`
- 保持 `EmbedAllFonts=true`

这套参数的优点是：

- 体积相对原始 `20M` 明显下降，实测约 `980K`
- 字体仍然是 `FZXBSJW` / `SimSun` / `KaiTi` / `SimHei`
- Ghostscript 重写后，PDF 内部对象结构更标准，**大概率**比 WPS 原始 PDF 更利于 macOS Preview 兼容

注意：最后一条是基于 PDF 重写机制的工程推断，不等同于对 Preview 的完整人工回归。上线前仍建议拿一批真实文档在 Preview 中抽样验证。

### 13.3 这轮 fix 还发现了一个隐藏问题

即使镜像里已经安装了 `ghostscript`，它在运行时也可能因为 `libtiff.so.5` 解析异常而无法启动。

当前项目里本来就有一条为 WPS 做的兼容链接：

- `libtiff.so.6 -> libtiff.so.5`

但如果没有执行 `ldconfig`，Ghostscript 仍可能报：

- `gs: error while loading shared libraries: libtiff.so.5: cannot open shared object file`

因此镜像和入口脚本里都应补上：

- `ldconfig`

否则服务会表现成：

- 转换能成功
- 字体也已经命中
- 但 PDF 后处理压缩根本没有生效

### 13.4 当前建议的生产策略

对于 `Word -> PDF` 场景，推荐使用下面这条流水线：

1. 上传 `.doc` / `.docx`
2. WPS Writer 打开并导出 PDF
3. 使用 Ghostscript 做二次重写与压缩
4. 如果压缩后更小，则替换原始 PDF；否则保留原始 PDF
5. 返回最终 PDF

这样做的原因是：

- 第一阶段先保住版式正确性
- 第二阶段再解决 Linux WPS 输出 PDF 体积过大问题
- 不需要魔改 `pywpsrpc`
- 可以把“压缩等级”作为服务层配置，而不是写死在绑定层

### 13.5 当前服务内已经收敛的 PDF profile

当前服务只保留一个最小配置面：

- `WPS_PDF_USE_GHOSTSCRIPT`

语义也只保留两档：

- `false`：直接返回 WPS 原始 PDF
- `true`：执行 Ghostscript 重写，固定使用 `150ppi`

这次收敛的原因是：

- 之前的多分辨率参数虽然灵活，但会把服务配置面拉得过大
- 现阶段更需要稳定、可解释、可部署的默认策略
- Word / PPT / Excel 三条链路共享同一套 PDF 后处理逻辑即可

## 14. 2026-03-08 接口收敛：从 `word-to-pdf` 到通用 `convert-to-pdf`

在确认 `Writer / Presentation / Spreadsheet` 三条路径都具备导出 PDF 的能力后，服务接口已收敛为更通用的形态。

### 14.1 外部接口

推荐使用：

- `POST /api/v1/convert-to-pdf`
- `POST /api/v1/convert-to-pdf/batch`

其中：

- 单文件接口直接返回 PDF
- 批量接口返回 ZIP

之所以没有把单文件和数组输入强行塞进同一个端点，是因为那样会导致响应语义变脏：

- 单文件时返回 PDF
- 多文件时返回 ZIP
- 出错时又返回 JSON

虽然“看起来统一”，但实际上增加了 SDK、文档和网关层的复杂度。因此采用方案 A 更符合 KISS。

### 14.2 内部架构

内部通过一个轻量注册表做格式分发：

- `.doc` / `.docx` -> Writer
- `.ppt` / `.pptx` -> Presentation
- `.xls` / `.xlsx` -> Spreadsheet

统一转换服务只做这些通用步骤：

1. 校验输入
2. 上传文件落盘
3. 选择对应适配器
4. 获取对应锁
5. 调用 WPS 自动化导出 PDF
6. 执行 Ghostscript 后处理
7. 写入元数据并返回结果

这样既避免了 route 层膨胀，也避免了把服务逻辑写进 `pywpsrpc` 绑定层。

### 14.3 批量与并发

批量接口已支持文件数组，但并发模型是受控的：

- 请求层允许并发调度多个文件
- 运行层按文档族加锁
- 同一族串行，不同族可并行

这是因为当前项目的本质仍然是“桌面应用的服务端自动化封装”，而不是原生高并发文档引擎。

如果未来要追求更高吞吐量，正确方向不是取消这些锁，而是：

- 多实例部署
- 按文档族拆服务
- 或引入有限 worker 池

## 15. 2026-03-08 真实样例回归：Word / PPT / Excel 已全部跑通

这轮已基于 `tests/files` 中的真实样例完成端到端回归：

- `tests/files/经责审计报告示例.docx` -> 成功，返回 PDF 约 `980K`
- `tests/files/123.pptx` -> 成功，返回 PDF 约 `835K`
- `tests/files/456.xls` -> 成功，返回 PDF 约 `58K`

同时也验证了批量接口：

- `POST /api/v1/convert-to-pdf/batch`
- 同时上传 `docx + pptx + xls` 三个文件
- 成功返回 ZIP，内含 `outputs/*.pdf` 与 `manifest.json`

### 15.1 最终打通的关键点

这次不是继续改 API，而是把运行时补到位：

- 用 `Xorg + dummy driver` 替换原先的 `Xvfb`
- 在 `entrypoint` 启动前清理遗留 X 锁，避免热重启后 `display :99` 被占用
- `PresentationAdapter` 中把 `SlideShowName` 从 `None` 改为 `""`
- `SpreadsheetAdapter` 中对 `app.Workbooks` 增加短重试
- `SpreadsheetAdapter` 的 PDF 导出改为最小参数：`ExportAsFixedFormat(xlTypePDF, outputPath)`

其中，Excel 路径的关键经验是：

- 问题并不只在“能否拉起 ET”
- 即使 `getEtApplication()` 成功，导出参数过重也可能失败
- 对当前这套 WPS Linux 运行时，最小导出参数更稳定

### 15.2 当前可交付能力

截至 `2026-03-08`，这个项目已经可以稳定对外提供：

- `doc` / `docx` -> PDF
- `ppt` / `pptx` -> PDF
- `xls` / `xlsx` -> PDF

并且具备以下工程能力：

- 通用单文件接口：`POST /api/v1/convert-to-pdf`
- 批量接口：`POST /api/v1/convert-to-pdf/batch`
- 按文档族加锁，避免同族自动化通道相互干扰
- Ghostscript 后处理，降低 PDF 体积并改善兼容性
- 外挂中文字体目录，改善字形还原与 macOS Preview 兼容性

### 15.3 阶段性结论

现在最准确的结论已经不再是“PPT / Excel 卡在运行时”，而是：

- 接口层已收敛完成
- 容器运行时已调整完成
- `Writer / Presentation / Spreadsheet` 三条路径都已通过真实样例验证
- 当前这套方案已经具备作为统一 PDF 转换服务继续演进的基础
