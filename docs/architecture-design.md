# 智能教育平台架构设计

状态为 v0.3，更新于 2026-11-12。具体依赖和变更依据见[技术栈与选型记录](technology-stack.md)，开发进度见开发日志。

## 已确定的框架方向

| 层 | 框架 | 职责 |
| --- | --- | --- |
| 前端 | Vue | 管理端与教师端页面、教师 Agent 对话、生成任务进度与成果展示。学生端在教师端验收后启动。 |
| 后端 | FastAPI | 认证与权限校验、业务接口、Agent 会话接口，以及任务和成果的查询。 |
| Agent | LangChain Deep Agents Python SDK | 根据教师意图与所选上下文选择和串联业务工具，向对话返回任务状态和成果。 |

FastAPI 提供 OpenAPI 接口描述，Deep Agents 支持传入自定义工具。项目可以用后者注册教学操作，在两个入口复用同一套服务与权限校验。[Vue 文档](https://vuejs.org/guide/introduction.html) · [FastAPI 功能文档](https://fastapi.tiangolo.com/features/) · [Deep Agents 文档](https://docs.langchain.com/oss/python/deepagents/overview)

## 模块关系

```mermaid
flowchart LR
    TeacherPages["Vue 教师功能页"] --> BusinessAPI["FastAPI 业务接口"]
    AdminPages["独立 Vue 管理端"] --> BusinessAPI
    Chat["Vue 教师 Agent 对话"] --> AgentAPI["FastAPI 会话接口"]
    AgentAPI --> DeepAgents["Deep Agents"]
    DeepAgents --> Tools["教学工具"]
    Tools --> Services["业务服务"]
    BusinessAPI --> Services
    Services --> Records["业务数据与成果"]
    Services --> Jobs["耗时任务"]
    Jobs --> Records
```

1. **业务服务**负责课程与任课关系、素材和成果版本、试卷与作业、批改和学情。页面接口与 Agent 工具均调用业务服务，服务端按当前教师、学校、课程及教学班进行授权。
2. **工具调用**接受结构化参数与业务对象 ID。课程上下文由服务端校验。长任务返回任务 ID，页面和对话查询同一状态，成功后跳转到相同的成果版本。已确认成绩和公开反馈通过功能页完成。
3. **会话状态**保存教师可见的对话历史、所选业务上下文与工具执行结果。原始资料与教学成果保存在业务记录中。重试按任务标识查询或恢复已有操作，避免重复生成、批改或写入成绩。
4. **数字课程**由专用页面经业务接口编排。生成逐页口播稿、上传形象和参考语音、预览、渲染与导出均在该页面完成。Agent 可以提供页面入口。形象与参考音频按业务权限访问和使用。

## 待讨论的技术决策

- 首个验证组件为教案生成。用同一课程和资料，从功能页和对话分别提交生成请求，验证权限、任务状态、草稿记录和编辑行为。
- 后续按组件比较前端工程配套、数据库与对象存储、后台任务执行与重试、对话流式传输与会话持久化、模型与教学内容生成、数字人及语音方案。对比结论与验收样例按组件记录，确认后实施。

## 首次开发实现

- Vite 多入口构建。教师端入口是 `/`，学校管理端入口是 `/admin/`。教师 Agent 使用教师端独立全页路由。
- FastAPI 提供同源 API。学校管理员和教师使用不同入口，后端校验账号角色、服务端会话、任课关系和资料或教案归属。
- SQLAlchemy 支持 SQLite 本地验收和 PostgreSQL 部署配置。资料原件位于私有目录，数据库保存逐页正文、树形目录和教案版本号。编辑使用带预期版本号的更新防止覆盖。
- 教案使用 DOCX Editor 进行分页编辑，已有结构化教案通过生成 DOCX 打开。Word 模板与实例独立保存。文本索引用于教师 Agent 查询，DOCX 为编辑和导出的正文版本。续写与重写调用独立的模型服务接口。
- 资料、教案和 Word 模板使用同一 PDF.js 连续滚动预览。旧 DOC 转换与导出、Word 模板预览及新版教案 PDF 导出依赖 LibreOffice。
- Agent 在当前课程范围内读取资料列表、目录、页码正文和已有教案。Skill 指导工具选择和引用。向量召回及 Agent 保存能力待后续实现。
