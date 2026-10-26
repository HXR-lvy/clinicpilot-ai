# ClinicPilot AI 对话工作总结

> 总结日期：2026-10-26
> 工作目录：`E:\drkudos`
> Public GitHub：https://github.com/HXR-lvy/clinicpilot-ai
> 功能完成提交：`68d5e02`（`Complete REST tools summaries and observability`）

## 1. 本次对话完成的目标

本次对话从阅读一份 AI 软件工程师 Take-Home 作业开始，依次完成了以下工作：

1. 翻译并分析 `AI-interview-take-home-assignment.md`。
2. 检查 `dkl_ai_interview_data` 中的 6 个 CSV 数据集。
3. 根据实际数据、运行环境和交付时间制定 24 小时实施计划。
4. 从空目录创建完整的 ClinicPilot AI 端到端 MVP。
5. 实现 FastAPI、SQLite 数据持久化、TF-IDF 混合检索、AI 路由与多轮预约状态机。
6. 实现 React 聊天工作台和实时预约列表。
7. 完成自动测试、API 实测、浏览器交互验收和冷启动持久化验证。
8. 修复验收中发现的检索准确性与患者上下文问题。
9. 编写 README、技术设计文档和本总结文档。
10. 初始化 Git 并创建本地提交。
11. 提供项目的手动运行和 DeepSeek 配置说明。
12. 将预约查询和创建工具改为通过公开 REST API 执行。
13. 增加医疗文本结构化摘要接口。
14. 增加 FastAPI、SQLite、REST 工具和 DeepSeek 调用的 OpenTelemetry 追踪。
15. 根据用户确认，取消 Docker/Kubernetes 容器化项。

## 2. 作业要求分析与结论

作业要求实现一个名为 ClinicPilot AI 的诊所智能助手原型，核心目标是完成以下闭环：

```text
诊所/医生/治疗问答
    -> 基于 CSV 数据的治疗和医生推荐
    -> 查询固定患者的已有预约
    -> 多轮收集预约参数
    -> 调用工具创建预约
    -> 将记录持久化到数据库
    -> 前端重新读取并显示新预约
```

分析后的关键判断：

- 招聘方最重视架构清晰度、意图路由、AI 工具调用质量和数据库持久化。
- 复杂 UI 美化不是重点，功能完整和现场演示稳定性更重要。
- 患者固定为 `P001` (John Doe)，不要求登录或患者 ID 输入。
- 不要求排班冲突、支付、取消预约或真实医疗诊断。
- 必须提供 `POST /api/chat`、`POST /api/bookings`、`GET /api/bookings`。
- 必须提供 `README.md`、`TECH_DOC.md`，并准备面试现场 Demo。
- Bonus 不影响核心闭环的优先级。

## 3. 数据集检查结果

数据目录：`E:\drkudos\dkl_ai_interview_data`

| 文件 | 行数 | 主要内容 |
|---|---:|---|
| `clinics.csv` | 2 | 诊所地址、营业时间、取消政策和急诊指引 |
| `doctors.csv` | 4 | 医生专长、语言、费用和简介 |
| `treatments.csv` | 5 | 治疗项目、类别、时长、价格和准备说明 |
| `patients.csv` | 3 | 患者资料和过敏记录 |
| `patient_bookings.csv` | 4 | 初始预约记录 |
| `patient_treatment_history.csv` | 2 | 历史就诊、诊断、用药和医生备注 |

合计 20 条源数据。

关键发现：

- 默认患者 `P001` 为 John Doe。
- `P001` 的已知过敏史为 `Penicillin, Peanuts`。
- `P001` 的初始预约为：
  - `B1001`：2026-11-05 09:00，D101 / T001。
  - `B1004`：2026-11-15 11:00，D104 / T005。
- CSV 没有医生与治疗项目的显式关联字段，因此建立了以下映射：

| 医生 | 可提供治疗 |
|---|---|
| `D101` | `T001`, `T004` |
| `D102` | `T002` |
| `D103` | `T003` |
| `D104` | `T005` |

- 当前时间上下文为 2026-10-26，因此患者的下一预约应为 `B1001`。
- 当前目录最初不是 Git 仓库。
- 机器已有 Python 3.13.2、Node.js 24 和 npm 11，但没有 `uv`、Docker 或 DeepSeek API Key。

## 4. 24 小时方案与最终技术选择

最终选择如下：

| 维度 | 选择 |
|---|---|
| 后端 | FastAPI 单体分层架构 |
| 数据库 | SQLite + SQLAlchemy |
| 前端 | React 19 + Vite + TypeScript |
| RAG | SQLite 精确查询 + 本地 TF-IDF 检索 |
| AI 编排 | 显式意图路由 + 自定义预约状态机 |
| 模型接口 | DeepSeek OpenAI 兼容接口 |
| 测试 | Pytest + FastAPI TestClient + 前端生产构建 |
| 开发降级 | Mock LLM，可在无 Key 时完成全部核心流程 |
| Bonus | 实现摘要与 OpenTelemetry；按用户要求取消容器化 |

24 小时计划的主要里程碑：

1. 初始化项目、复制 CSV、建立数据库模型。
2. 完成预约查询、创建和输入校验。
3. 完成 TF-IDF 检索与患者上下文加载。
4. 完成意图路由、多轮预约、工具调用和落库。
5. 完成 React 工作台。
6. 完成端到端测试和错误处理。
7. 完成 README、技术文档、彩排和提交。

## 5. 实际实现内容

### 5.1 后端与数据库

创建了 FastAPI 后端，包含以下表：

- `clinics`
- `doctors`
- `treatments`
- `patients`
- `patient_bookings`
- `patient_treatment_history`
- `doctor_treatments`
- `conversations`
- `messages`
- `booking_drafts`

实现能力：

- 从 CSV 幂等导入数据。
- 启动时自动建表并补齐种子数据。
- 支持 `python -m app.seed --reset` 恢复初始数据库。
- 保存对话、消息、预约草稿和最终预约。
- 新预约使用 `B1005` 这类可读编号。
- `draft_id` 唯一约束用于防止工具重试导致重复预约。

### 5.2 公共 API

```http
POST /api/chat
POST /api/bookings
GET  /api/bookings?patient_id=P001
GET  /api/health
```

`POST /api/chat` 返回：

- 会话 ID；
- 助手消息；
- 意图；
- 会话状态；
- 检索来源；
- 当前预约草稿；
- 已创建预约；
- 是否需要确认；
- 当前 LLM 模式。

异常处理：

- 未知患者、医生、治疗或会话返回 `404`。
- 医生/治疗组合不兼容或请求校验失败返回 `422`。
- 重复提交相同 `draft_id` 返回已有预约，不重复插入。

### 5.3 RAG 与推荐

实现了本地混合检索：

1. 将诊所政策、医生信息、治疗说明构建为文本文档。
2. 使用本地 TF-IDF 和余弦相似度召回 Top 6。
3. 使用 SQLite 读取准确的价格、ID、时间和关联字段。
4. 针对常见症状增加同义词扩展，例如：
   - `skin/rash` -> Dermatology；
   - `knee/joint` -> Orthopedics；
   - `child/vaccine` -> Pediatrics；
   - `flu/shot` -> Immunization。
5. 返回诊所、医生和治疗来源 ID，方便前端展示和人工核验。
6. 推荐结果只使用现有服务，不进行诊断或处方。

### 5.4 意图识别与预约状态机

支持的意图：

- `qa_recommendation`
- `booking_lookup`
- `booking_create`
- `small_talk`

预约状态：

```text
idle
  -> collecting
  -> awaiting_confirmation
  -> booking
  -> completed
```

工作方式：

- 缺少医生、治疗、日期或时间时，保存草稿并自然追问。
- 医生或治疗只有唯一合法对应项时，自动补齐另一项。
- 所有参数齐全后，显示预约摘要并要求明确确认。
- 用户回复 `yes` 后才创建预约。
- 用户明确拒绝时取消草稿，不写入预约。
- 已完成后再次确认不会重复创建预约。

### 5.5 LLM 与工具执行

实现了一个可替换的模型层：

- `LLM_MODE=live`：使用 DeepSeek OpenAI 兼容接口。
- `LLM_MODE=mock`：使用确定性关键词路由，适合本地开发和测试。
- 启用 `LLM_FALLBACK_TO_MOCK=true` 时，外部模型失败可降级到 mock。
- DeepSeek 使用 `deepseek-flash`、非思考模式和 JSON 路由输出。
- 模型输出由 Pydantic 再次校验，模型不能直接操作数据库。

可执行领域工具：

- `search_clinic_knowledge`
- `get_patient_bookings`：通过 `GET /api/bookings` 执行
- `upsert_booking_draft`
- `create_booking`：通过 `POST /api/bookings` 执行
- `cancel_booking_draft`

Agent 不再直接通过 ORM 查询或创建预约。REST 客户端负责解析响应并映射错误：

- `404`：业务实体不存在。
- `422`：业务校验失败。
- 网络、服务端或响应格式错误：`503`。

预约创建失败时，草稿和会话保持 `awaiting_confirmation`，用户再次确认后可使用相同 `draft_id` 安全重试。

### 5.6 患者上下文与医疗安全

- 每次对话都加载 `P001` 的过敏史、预约和治疗历史。
- “下一次预约”严格查询数据库，而不是依赖模型记忆。
- 花生过敏预约会引用已知过敏信息，并限定为诊所预约，不提供诊断。
- 对胸痛、呼吸困难、严重出血等红旗描述返回急诊指引并中止预约。
- UI 明确说明系统是预约与信息助手，不替代医生。

### 5.7 React 前端

创建了英文双栏工作台：

- 左侧为交互式聊天面板。
- 右侧为患者预约列表。
- 显示当前意图、会话状态、LLM 模式和来源 ID。
- 每条助手回复后从 `GET /api/bookings` 重新读取数据库。
- 支持预约列表手动刷新。
- 支持创建新会话。
- 提供营业时间、皮肤症状和预约查询快捷问题。
- 响应式布局，在窄屏下自动上下排列。

### 5.8 医疗文本摘要

新增 `POST /api/summarize`：

- 接收最多 20,000 字符的 `transcript`。
- 固定返回 `chief_complaint`、`diagnosis`、`medication` 和 `doctor_instructions`。
- Mock 模式使用确定性标签提取；live 模式要求 DeepSeek 返回可校验 JSON。
- 接口无状态，不持久化原始医疗文本或摘要。
- 文档明确该工具只整理已有信息，不替代医生诊断。

### 5.9 OpenTelemetry 可观测性

- 自动追踪 FastAPI 请求和 SQLAlchemy 数据库操作。
- REST 工具报告工具名、传输方式、耗时和结果数量。
- DeepSeek 路由、回答和摘要报告模型、操作、耗时、Token 和错误状态。
- 支持可选 OTLP HTTP 导出，也可使用控制台导出。
- 不把完整提示词、用户消息或医疗文本写入 span 属性。
- 按用户要求，不包含 Docker/Kubernetes 部署。

## 6. 测试与验收结果

### 6.1 自动测试

后端最终测试结果：

```text
28 passed, 1 warning in 2.32s
```

测试覆盖：

- 健康检查和种子预约。
- 下一次预约识别。
- REST 工具使用正确的 GET/POST 路径、查询参数和请求体。
- REST `404`、`422`、`500`、网络异常和 `503` 映射。
- 多轮预约收集与确认。
- 创建预约后数据库持久化。
- 创建失败后保留草稿并可重试。
- 后端重启后预约仍存在。
- 医生/治疗不兼容校验。
- `draft_id` 幂等创建。
- 急诊红旗中止预约。
- 未知患者 `404`。
- 诊所实体名称检索正确性。
- 花生过敏上下文引用。
- 无 Key 的 live 模式安全降级。
- 皮肤症状推荐 Dermatology。
- 日期、时间和确认短语解析。
- 医疗文本摘要结构、输入校验和无状态行为。
- FastAPI、SQLite、REST 工具和 DeepSeek span，Token 属性及内容脱敏。

唯一警告是 FastAPI/Starlette TestClient 对 httpx 的弃用提示，不影响测试结果和运行。

### 6.2 前端验证

```text
TypeScript 检查通过
Vite 生产构建通过
30 modules transformed
```

### 6.3 API 实测

使用实际运行的 FastAPI 完成了：

```text
查询下一次预约
    -> 返回 B1001
发起一般健康检查预约
    -> collecting
提供日期和时间
    -> awaiting_confirmation
回复 yes
    -> completed
    -> 创建 B1005
GET /api/bookings
    -> 返回数据库中的新预约
```

服务日志进一步确认：

```text
POST /api/bookings HTTP/1.1 201 Created
agent_tool name=create_booking transport=rest
```

### 6.4 浏览器验收

使用本地浏览器验证了：

- 页面可成功加载。
- 聊天快捷问题可发送。
- 助手回复和来源标签正常显示。
- 意图和状态标签正常更新。
- 右侧预约列表能够显示数据库记录。
- 响应式布局在窄视口下正常工作。

## 7. 验收中发现并修复的问题

### 7.1 TF-IDF 向量生成错误

初次测试发现列表推导式中变量名错误，导致检索初始化抛出 `NameError`。修正后检索和聊天测试通过。

### 7.2 诊所名称检索错误

浏览器实测发现询问 “Metro Care's opening hours” 时，mock 回答错误选中 Sunset Wellness Center。修复方式：

- 增加文档标题实体词匹配加分。
- clinic 回答选择时优先匹配查询中出现的诊所名称。
- 增加对应回归测试。

修复后正确返回 `Metro Care Health Clinic` 和来源 `C001`。

### 7.3 花生过敏上下文未出现在追问中

最初只创建了正确的 D101/T001 草稿，但追问日期时间时没有提及过敏史。修复后追问会包含：

```text
I have your known allergies on file: Penicillin, Peanuts.
```

同时明确说明这是诊所预约，不是诊断。

### 7.4 Python 虚拟环境与 pytest 临时目录问题

执行环境限制导致 `ensurepip` 和 pytest 默认临时目录权限失败。处理方式：

- 将虚拟环境创建时的临时目录指向项目内 `.tmp`。
- 将 pytest 的 `--basetemp` 固定到 `backend/.pytest-tmp`。
- 两个目录均已加入 `.gitignore`。

## 8. 文档与版本控制

已创建或更新：

- `README.md`：安装、运行、DeepSeek 配置、Demo 流程和测试说明。
- `TECH_DOC.md`：架构、意图识别、状态机、工具、RAG 和数据库设计。
- `.env.example`：安全的默认环境变量模板。
- `PROJECT_SUMMARY.md`：本对话和项目工作的完整总结。

Git 工作：

- 初始化了新仓库。
- 初始提交：`513f19e`（`Build ClinicPilot AI appointment MVP`）。
- 功能完成提交：`68d5e02`（`Complete REST tools summaries and observability`）。
- 初始提交包含 47 个文件、6116 行新增内容。
- 已创建并推送 Public GitHub 仓库：
  `https://github.com/HXR-lvy/clinicpilot-ai`。
- 远端验证结果为 `visibility=public`、默认分支 `master`。

## 9. 当前项目状态

- 当前代码位于 `E:\drkudos`。
- 本地与远端仓库均使用 `master` 分支。
- 已完成 Public GitHub 发布。
- 默认运行模式为 `LLM_MODE=mock`。
- 测试和实测产生的额外预约已清理。
- 当前数据库已恢复为种子状态：
  - 患者 `P001` 只有 `B1001` 和 `B1004`。
- 后端和前端开发服务器在验收后均已停止。
- `.venv` 和 `frontend/node_modules` 已安装但被 Git 忽略。

## 10. 手动运行方式

### 终端 1：后端

```powershell
cd E:\drkudos\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

可用地址：

- 健康检查：http://localhost:8000/api/health
- OpenAPI：http://localhost:8000/docs

### 终端 2：前端

```powershell
cd E:\drkudos\frontend
npm run dev
```

打开：

http://localhost:5173

### 恢复初始数据库

```powershell
cd E:\drkudos\backend
..\.venv\Scripts\python.exe -m app.seed --reset
```

### 使用真实 DeepSeek

在仓库根目录执行：

```powershell
cd E:\drkudos
Copy-Item .env.example .env
```

修改 `.env`：

```text
LLM_MODE=live
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
LLM_FALLBACK_TO_MOCK=true
```

然后重启后端。

## 11. 尚未完成或需要外部条件的事项

1. 当前没有有效 DeepSeek API Key，因此真实模型调用由用户后续完成最终联网验收。
2. 当前仍是固定单患者演示，不包含认证、权限、真实排班冲突、支付或 EHR 集成；这些不属于作业核心要求。
3. Docker/Kubernetes 容器化已由用户明确取消，不再作为交付项。

## 12. 交付文件索引

- [README.md](README.md)：本地安装与运行指南。
- [TECH_DOC.md](TECH_DOC.md)：技术架构与设计说明。
- [.env.example](.env.example)：环境变量模板。
- [backend/app/main.py](backend/app/main.py)：FastAPI 入口和公共接口。
- [backend/app/chat.py](backend/app/chat.py)：对话、状态机和领域工具。
- [backend/app/booking_tools.py](backend/app/booking_tools.py)：Agent 的 REST 预约工具。
- [backend/app/summary.py](backend/app/summary.py)：结构化医疗文本摘要。
- [backend/app/observability.py](backend/app/observability.py)：OpenTelemetry 初始化与 instrumentation。
- [backend/app/llm.py](backend/app/llm.py)：DeepSeek 和 mock 路由。
- [backend/app/retrieval.py](backend/app/retrieval.py)：TF-IDF 混合检索。
- [backend/app/seed.py](backend/app/seed.py)：数据库初始化和 CSV 导入。
- [frontend/src/App.tsx](frontend/src/App.tsx)：React 工作台主界面。
- [backend/tests](backend/tests)：后端自动测试。

