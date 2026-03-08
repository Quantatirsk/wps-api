# WPS API 服务开发方案

## 1. 目标与原则

本方案基于当前仓库已有的容器运行基础与 `pywpsrpc` 能力，目标是在**不魔改 `pywpsrpc` 核心绑定层**的前提下，把本项目演进为一个可维护、可扩展、可部署的 WPS API 服务。

遵循的基本原则如下：

- 保持职责分层：`pywpsrpc` 负责 WPS RPC 调用，服务层负责 HTTP、任务控制、日志、鉴权与资源治理。
- 先做最小闭环：优先完成 `Word -> PDF`，再扩展到 PPT / Excel。
- 避免过早复杂化：第一阶段不引入消息队列、分布式调度、复杂多租户策略。
- 保持可替换性：未来既可以继续使用当前仓库承载服务代码，也可以把服务层单独拆仓。
- 面向运行稳定性设计：优先解决 WPS 进程管理、超时、并发互斥、临时文件清理。

## 2. 推荐方案结论

在“新起一个项目引用库”与“直接在库基础上魔改”之间，推荐采用下面的落地方式：

> 以当前仓库作为运行时基础，在仓库内新增独立的服务层代码，把 `pywpsrpc` 当作依赖使用，而不是把 HTTP 服务逻辑写进 `pywpsrpc` 本身。

这是一个折中的最优方案，原因是：

- 不破坏 `pywpsrpc` 的库定位。
- 不增加未来同步上游库的维护成本。
- 便于直接复用当前仓库现成的 Docker 运行环境。
- 交付最快，试错成本最低。
- 后续如果要拆成独立服务仓库，迁移成本也很低。

换句话说，建议把当前仓库演进成：

- `runtime` 层：WPS + Xvfb + dbus + pywpsrpc
- `service` 层：FastAPI + 任务治理 + 文件管理 + 接口暴露

而不是：

- 把 FastAPI、上传下载、鉴权、任务调度直接塞进 `pywpsrpc`

## 3. 范围定义

## 3.1 第一阶段范围（必须做）

第一阶段只做最小可用产品（MVP），范围控制为：

- `GET /api/v1/healthz`
- `GET /api/v1/readyz`
- `POST /api/v1/convert-to-pdf`
- 上传单个 `.doc` / `.docx`
- 返回单个 PDF 文件流
- 基础错误处理
- 任务目录隔离
- Writer 级别互斥锁
- 基础日志
- 容器化启动

## 3.2 第二阶段范围（建议做）

在第一阶段稳定后扩展：

- `POST /api/v1/convert/ppt-to-pdf`
- `POST /api/v1/convert/excel-to-pdf`
- API Key 鉴权
- 更清晰的错误码模型
- 超时控制与任务取消
- 转换耗时统计
- 输出文件持久化到对象存储

## 3.3 第三阶段范围（按需做）

- 异步任务模式
- 回调通知
- 批量转换
- 工作流编排
- 多实例 worker 池
- 水印、页眉页脚、内容预处理
- 文档审计与事件触发器

## 4. 总体架构设计

推荐采用单体服务、内部清晰分层的架构。

### 4.1 逻辑分层

```text
Client
  -> FastAPI Router
    -> Application Service
      -> WPS Adapter (pywpsrpc 封装)
        -> WPS Process in Xvfb/dbus container
```

各层职责如下：

- Router 层：处理 HTTP 协议、入参校验、文件上传下载、状态码映射。
- Application Service 层：负责任务目录、锁、超时、异常归一化、日志上下文。
- WPS Adapter 层：只封装 `pywpsrpc` 调用，不感知 HTTP。
- Runtime 层：负责 Xvfb、dbus、字体、WPS 本体。

### 4.2 目录建议

```text
.
├── Dockerfile
├── docker/
│   └── entrypoint.sh
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── api/
│   │   ├── health.py
│   │   └── convert.py
│   ├── services/
│   │   ├── conversion_service.py
│   │   └── job_service.py
│   ├── adapters/
│   │   ├── writer_adapter.py
│   │   ├── presentation_adapter.py
│   │   └── spreadsheet_adapter.py
│   └── utils/
│       ├── files.py
│       ├── locks.py
│       ├── logging.py
│       └── errors.py
└── docs/
    ├── wps-server-research.md
    └── api-service-development-plan.md
```

## 5. 模块设计

## 5.1 `app/main.py`

职责：

- 创建 FastAPI 实例
- 注册路由
- 注册中间件
- 注册启动 / 关闭生命周期事件

建议：

- 启动时做最小自检，但不要在启动阶段真正打开文档转换。
- 保持入口尽量薄，不写业务逻辑。

## 5.2 `app/api/convert.py`

职责：

- 提供 `/api/v1/convert-to-pdf`
- 校验上传文件后缀与 MIME
- 调用 `conversion_service`
- 将异常映射为统一 JSON 错误响应
- 成功时返回 `FileResponse`

注意：

- 不在路由里直接写 `pywpsrpc` 调用。
- 不在路由里做目录清理、锁控制、进程回收等复杂逻辑。

## 5.3 `app/services/conversion_service.py`

职责：

- 编排单次转换流程
- 创建任务目录
- 保存上传文件
- 获取对应类型锁
- 调用 Writer Adapter
- 记录耗时与结果
- 返回输出文件路径
- 在失败时清理临时资源

这是第一阶段的核心业务层。

## 5.4 `app/adapters/writer_adapter.py`

职责：

- 封装 Writer 相关 `pywpsrpc` 调用
- 创建 `QtApp`
- 获取 WPS Application
- 打开文档
- 调用 `SaveAs2(..., FileFormat=wdFormatPDF)`
- 关闭文档与应用
- 抛出统一内部异常

设计要求：

- 只做同步 WPS 操作
- 不直接依赖 FastAPI 类型
- 不关心 HTTP 请求对象

## 5.5 `app/utils/locks.py`

职责：

- 提供 Writer / WPP / ET 级别互斥锁

第一阶段建议：

- 用单进程内 `asyncio.Lock`
- 先解决“同实例不可并发调用”的问题

第二阶段可升级为：

- 文件锁
- Redis 锁
- Worker 队列

## 5.6 `app/utils/files.py`

职责：

- 生成任务目录
- 写入上传文件
- 约定输出路径
- 清理过期任务目录

路径建议：

- `/workspace/jobs/<job_id>/input.docx`
- `/workspace/jobs/<job_id>/output.pdf`
- `/workspace/jobs/<job_id>/meta.json`

## 5.7 `app/utils/errors.py`

职责：

- 定义统一错误类型
- 区分参数错误、转换失败、环境错误、超时错误
- 供 API 层映射为标准响应

建议错误分类：

- `InvalidInputError`
- `UnsupportedFormatError`
- `WpsStartupError`
- `WpsOpenDocumentError`
- `WpsConversionError`
- `ConversionTimeoutError`

## 6. API 设计

## 6.1 `GET /api/v1/healthz`

用途：

- 仅用于说明服务进程存活

返回示例：

```json
{"ok": true}
```

## 6.2 `GET /api/v1/readyz`

用途：

- 检查运行环境是否处于可接单状态

第一阶段建议检查：

- 工作目录可写
- `DISPLAY` 已设置
- `XDG_RUNTIME_DIR` 可写
- `pywpsrpc` 可导入

注意：

- 第一阶段不建议在 `readyz` 中真实发起 WPS 文档转换，避免探针引起副作用。

## 6.3 `POST /api/v1/convert-to-pdf`

请求：

- `multipart/form-data`
- 字段：`file`

支持输入：

- `.doc`
- `.docx`

响应：

- 成功：返回 `application/pdf`
- 失败：返回 JSON

错误响应示例：

```json
{
  "error": {
    "code": "WPS_CONVERSION_FAILED",
    "message": "failed to convert word document to pdf"
  }
}
```

## 7. 容器改造方案

## 7.1 Dockerfile 改造目标

当前 `Dockerfile` 已经能证明运行链路，但要改造成服务镜像，需要补足：

- API 依赖
- 独立入口脚本
- 工作目录
- 健康检查
- 日志输出一致性
- 可扩展的代码复制路径

## 7.2 entrypoint 设计

`docker/entrypoint.sh` 负责：

- 初始化 `XDG_RUNTIME_DIR`
- 启动 `Xvfb`
- 启动 `dbus` session
- 注入运行环境变量
- `exec` 启动 API 进程
- 捕获退出信号并清理子进程

## 7.3 运行约束

第一阶段建议：

- 一个容器实例只跑一个 API 进程
- 一个容器内对 Writer 转换串行化
- 不在一个实例内做高并发并行转换

## 8. 关键工程策略

## 8.1 并发策略

第一阶段：

- 使用 `asyncio.Lock` 将 Writer 转换串行化

原因：

- WPS 是桌面应用，不是线程安全的无状态转换引擎
- 先保证稳定，再考虑扩容

扩容方式：

- 通过容器副本横向扩容
- 使用负载均衡在实例间分发请求

## 8.2 超时策略

第一阶段必须加入超时保护：

- HTTP 请求级超时
- WPS 转换级超时

建议：

- 使用 `asyncio.wait_for` 或线程执行超时包装
- 超时后标记任务失败，并尽量回收 WPS 进程

## 8.3 清理策略

第一阶段至少要保证：

- 单次任务失败后删除临时目录
- 服务启动时可清理历史过期任务
- WPS 子进程异常残留时可被回收

## 8.4 日志策略

第一阶段建议记录：

- `job_id`
- 输入文件名
- 输入扩展名
- 转换类型
- 耗时
- 是否成功
- WPS PID
- 错误代码

## 8.5 字体策略

为了让 PDF 输出更稳定，建议在镜像中补充：

- `fonts-noto-cjk`
- 常见 Office 兼容字体
- 统一 locale

并准备一套测试文档验证：

- 中文
- 英文
- 表格
- 图片
- 页眉页脚
- 特殊字体

## 9. 里程碑拆分

## Milestone 1：服务骨架

目标：服务可启动、健康检查可用。

交付：

- `app/main.py`
- `app/api/health.py`
- `docker/entrypoint.sh`
- 改造后的 `Dockerfile`

验收：

- 容器能启动
- `/healthz` 返回 200
- `/readyz` 返回 200

## Milestone 2：Word 转 PDF 闭环

目标：跑通单文件转换。

交付：

- `app/api/convert.py`
- `app/services/conversion_service.py`
- `app/adapters/writer_adapter.py`
- `app/utils/files.py`
- `app/utils/locks.py`
- 错误定义与日志

验收：

- 上传 `.docx` 能返回 PDF
- 转换失败返回结构化错误
- 并发请求下保持串行执行且不崩溃

## Milestone 3：稳定性增强

目标：减少偶发失败，具备初步上线能力。

交付：

- 超时控制
- 启动清理逻辑
- 统一日志上下文
- 更完整的 ready 检查
- 样本文档回归脚本

验收：

- 连续转换多次无明显残留进程
- 超时任务可恢复
- 基础回归测试可重复执行

## Milestone 4：多格式扩展

目标：扩展到 PPT / Excel。

交付：

- `presentation_adapter.py`
- `spreadsheet_adapter.py`
- `/api/v1/convert/ppt-to-pdf`
- `/api/v1/convert/excel-to-pdf`

验收：

- `ppt/pptx -> pdf` 可用
- `xls/xlsx -> pdf` 可用

## 10. 测试方案

第一阶段建议补三类测试：

- 单元测试：路径生成、错误映射、参数校验、锁逻辑
- 集成测试：FastAPI 接口层，使用 mock 替代实际 WPS 调用
- 手工验证：在容器内用真实文档做端到端转换

说明：

- `pywpsrpc` 与 WPS 本体耦合较深，真实转换测试不适合完全依赖 CI
- 可先把“真实 WPS 验证”设计成手工 smoke test 或受控环境测试

## 11. 风险清单

主要风险包括：

- WPS 在 headless 环境下的稳定性不如专用转换引擎
- 字体缺失导致版式偏差
- 某些复杂 Office 文档兼容性不足
- 子进程异常残留
- 高并发下服务抖动
- 探针或异常恢复逻辑误伤正在运行的转换任务

对应策略：

- 限制第一阶段并发模型
- 准备标准样本文档集
- 加强日志与超时控制
- 保持接口单一、路径简单

## 12. 开发顺序建议

建议按以下顺序实施：

1. 改造 `Dockerfile` 和 `docker/entrypoint.sh`
2. 搭建 FastAPI 骨架与健康检查
3. 落地任务目录、锁、统一异常
4. 落地 Writer Adapter
5. 打通 `/api/v1/convert-to-pdf`
6. 做容器内真实文档转换验证
7. 再补超时、清理、日志增强
8. 最后扩展 PPT / Excel

## 13. 建议的下一步实施任务

如果立即进入开发阶段，建议从下面这些具体任务开始：

- 新增 `docker/entrypoint.sh`
- 新增 `app/main.py`
- 新增 `app/api/health.py`
- 新增 `app/api/convert.py`
- 新增 `app/services/conversion_service.py`
- 新增 `app/adapters/writer_adapter.py`
- 新增 `app/utils/files.py`
- 新增 `app/utils/locks.py`
- 新增 `app/utils/errors.py`
- 改造根目录 `Dockerfile`

这样可以在最短路径内得到一个真正能用的 `Word -> PDF` API 服务雏形。

## 14. 2026-03-08 落地修正：字体与 PDF 后处理

经过真实部署验证，`Word -> PDF` 这条链路需要明确补充两条工程策略。

### 14.1 字体策略必须升级为“宿主机挂载 + 容器内刷新缓存”

仅安装 `fonts-noto-cjk` 远远不够。对于中文公文、审计报告、政府文档、国企模板，往往会用到：

- 方正小标宋简体
- 方正仿宋简体
- 宋体
- 黑体
- 楷体
- 仿宋
- 微软雅黑

因此推荐的部署方式是：

- 宿主机维护字体目录，例如 `/opt/wps-api-service/zhFonts`
- 容器启动时只读挂载到 `/usr/local/share/fonts/zhFonts`
- 在 `entrypoint.sh` 中执行 `fc-cache`

这样字体升级、补字库、替换字体时，不需要重新构建镜像。

### 14.2 PDF 后处理应作为服务层标准步骤，而不是可有可无的附加动作

在 Linux WPS 场景下，光解决字体命中还不够，因为正确字体一旦嵌入，PDF 体积可能明显变大。

本项目当前的推荐链路是：

1. WPS 导出原始 PDF
2. 服务层用 Ghostscript 进行二次重写
3. 仅当优化后更小时，替换原始 PDF

这样做有几个直接好处：

- 减少 PDF 体积
- 改善跨阅读器兼容性
- 让压缩参数留在服务层配置，而不是耦合到 `pywpsrpc`

### 14.3 当前收敛后的 PDF profile

当前 PDF 后处理只保留两个档位：

- `WPS_PDF_USE_GHOSTSCRIPT=false`：不做 Ghostscript 重写，直接返回 WPS 原始 PDF
- `WPS_PDF_USE_GHOSTSCRIPT=true`：做 Ghostscript 重写，固定使用 `150ppi`

这样做的目标是：

- 配置面保持 KISS
- 避免把过多压缩旋钮暴露给服务层
- 统一 Word / PPT / Excel 三条链路的 PDF 后处理行为
- 默认保留一档更温和的压缩与兼容性优化

### 14.4 就绪探针需要覆盖 Ghostscript 可执行性

这次实测还发现一个容易漏掉的问题：镜像里虽然装了 `ghostscript`，但如果 `libtiff.so.5` 兼容链接没有被 `ldconfig` 刷新，`gs` 实际上无法启动。

因此当前方案中应同时保证：

- Docker 构建阶段执行 `ldconfig`
- 容器启动阶段再次执行 `ldconfig`
- `GET /api/v1/readyz` 检查 `gs --version` 能否正常执行

否则会出现“服务 ready、转换成功，但压缩未生效”的假阳性。

## 15. 2026-03-08 方案 A 落地：通用单文件与批量接口

当前服务已按方案 A 收敛为两个主接口：

- `POST /api/v1/convert-to-pdf`
- `POST /api/v1/convert-to-pdf/batch`

### 15.1 设计目标

这次重构遵循两个原则：

- **KISS**：外部接口只分“单文件”和“批量”两个语义，不把 PDF / ZIP / JSON 混在一个端点里。
- **Fail-Fast**：批量任务在执行前先校验所有文件类型；若存在不支持格式，直接失败，不进入实际转换。

### 15.2 支持格式

当前统一支持：

- Writer：`.doc`、`.docx`
- Presentation：`.ppt`、`.pptx`
- Spreadsheet：`.xls`、`.xlsx`

### 15.3 内部分发策略

服务层不在 route 里写大量 `if/else`，而是通过注册表统一分发：

- `writer` -> `WriterAdapter`
- `presentation` -> `PresentationAdapter`
- `spreadsheet` -> `SpreadsheetAdapter`

每条路由统一复用：

- 上传文件落盘
- 文件大小校验
- 超时控制
- 文档族级别互斥锁
- PDF 后处理压缩
- 元数据落盘

### 15.4 批量接口的并发策略

批量接口不是“无脑并发”。当前策略是：

- 批量请求中的文件会并发调度
- 但同一文档族会被对应锁串行化
- 不同文档族之间可以并行

这意味着：

- 多个 `docx` 不会同时挤进同一个 Writer 自动化通道
- `docx` 与 `pptx`、`xlsx` 可以在不同通道并发执行

这是当前阶段兼顾稳定性与吞吐量的最小复杂度方案。

### 15.5 批量返回格式

批量成功时返回一个 ZIP，其中包含：

- `outputs/*.pdf`
- `manifest.json`

`manifest.json` 记录：

- `batchId`
- `itemCount`
- 每个文件的 `jobId`
- `documentFamily`
- `inputFilename`
- `outputFilename`
- `durationMs`
- `processPid`
- `status`

当前版本采用“全成功才返回 ZIP”的策略：

- 如果某个文件转换失败，整个批量请求失败
- 已生成的中间文件会被清理

这比“部分成功、部分失败还返回混合结果”更符合当前的 KISS 目标。

### 15.6 当前实现边界

当前版本仍然刻意不做以下能力：

- 异步任务队列
- 回调通知
- 批量部分成功返回
- 单接口同时混合单文件与数组输入
- 高并发 worker 池

这些能力都不是做不到，而是当前阶段不值得引入额外复杂度。

## 16. 2026-03-08 回归验证结论：三条转换链路均已通过

基于 `tests/files` 中的真实样例，当前验证结果如下：

- `tests/files/经责审计报告示例.docx` -> 成功，输出约 `980K`
- `tests/files/123.pptx` -> 成功，输出约 `835K`
- `tests/files/456.xls` -> 成功，输出约 `58K`

### 16.1 单文件接口验证

已通过：

- `POST /api/v1/convert-to-pdf`

该接口现在已经验证覆盖：

- Writer 路径
- Presentation 路径
- Spreadsheet 路径

### 16.2 批量接口验证

已通过：

- `POST /api/v1/convert-to-pdf/batch`

使用 `docx + pptx + xls` 三个真实文件回归后，服务成功返回 ZIP，且包含：

- `outputs/*.pdf`
- `manifest.json`

`manifest.json` 中已正确记录每个文件的：

- `documentFamily`
- `inputFilename`
- `outputFilename`
- `durationMs`
- `processPid`
- `status=succeeded`

### 16.3 本轮真正解决的问题

最终打通 PPT / Excel 的关键不在 API 层，而在运行时与导出细节：

- 用 `Xorg + dummy driver` 替换 `Xvfb`
- 在容器启动时清理遗留 X 锁，避免 `display :99` 冲突
- `PresentationAdapter` 修正 `SlideShowName` 参数，传空字符串而不是 `None`
- `SpreadsheetAdapter` 为 `app.Workbooks` 增加短重试
- `SpreadsheetAdapter` 使用最小 PDF 导出参数，避免复杂参数组合导致失败

这也说明一个重要事实：

> 当前项目的主要难点不是“怎么做 FastAPI 封装”，而是“怎么把 WPS Linux 运行时调到稳定可自动化”。

### 16.4 当前可对外交付的能力边界

截至 `2026-03-08`，当前服务可以明确对外声明：

- `doc` / `docx` -> PDF：已通过
- `ppt` / `pptx` -> PDF：已通过
- `xls` / `xlsx` -> PDF：已通过
- 单文件转换：已通过
- 批量转换：已通过

### 16.5 当前版本仍保持的 KISS 边界

虽然三条链路都已跑通，但当前版本仍然刻意不做：

- 异步任务队列
- 结果回调
- 部分成功的批量返回
- 无限制并发 worker 池

原因不是能力缺失，而是当前阶段更优先保证：

- 运行时稳定性
- 版式一致性
- PDF 兼容性
- 服务边界清晰
