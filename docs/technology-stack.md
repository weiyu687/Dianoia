# Dianoia 技术栈与选型记录

更新于 2026-11-13。此文档记录实际依赖、外部运行条件及尚待选型的组件。前端依赖以 `frontend/package.json` 和 `frontend/package-lock.json` 为准，后端依赖以 `backend/requirements.txt` 和 `backend/requirements-agent.txt` 为准。

## 当前技术栈

| 模块 | 技术 | 用途与运行条件 |
| --- | --- | --- |
| 教师端与学校管理端 | Vue 3、Vue Router 4、Vite 7、Lucide Vue | 使用独立 Vue 入口，共用组件和同源 API。教师端包含独立的 Agent 页面。Node.js 使用 22.12 或更高版本。 |
| 业务 API | Python 3.12、FastAPI、Pydantic、Uvicorn | 请求校验、角色与任课关系校验、资料和教案接口。前后端开发时由 Vite 代理 `/api`。 |
| 认证 | Argon2id、数据库会话、HttpOnly Cookie | 学校管理员和教师使用角色匹配的登录入口。启用 HTTPS 时配置 Secure Cookie。 |
| 数据 | SQLAlchemy 2、SQLite、PostgreSQL 配置与 psycopg 3 | SQLite 用于本地验收。PostgreSQL 可通过环境配置接入，实际部署与迁移待验收。当前业务表在启动时创建。 |
| 虚拟数据导入 | openpyxl | XLSX 预检、导入和工号、学号及关联关系校验。 |
| 资料处理 | python-multipart、LibreOffice Writer/Impress、pypdf、python-pptx | Word 先转 PDF，再读书签和逐页正文。文本层 PDF 直接处理。PPTX 可提取原生文本并用 LibreOffice 生成 PDF 预览。资料原件保存在私有目录。 |
| PDF 查看 | PDF.js 5.4.624 | 资料、教案和模板共用原生 `PDFViewer`，支持连续滚动、按页渲染、页码同步和直接跳页。 |
| 教案文档 | `@docx-editor.dev/vue`、`core` 和 `i18n` 2.37.0，python-docx，LibreOffice | 分页在线编辑 DOCX，模板与教案副本在数据库存储。旧版 DOC 输入转为 DOCX，PDF 和 DOC 输出从当前文档版本转换。 |
| 旧教案兼容 | python-docx、ReportLab | 原有结构化教案可转换为 DOCX 打开。已有 PDF 导出在旧数据仍使用 ReportLab，首次在分页编辑器保存后使用 DOCX 转换。 |
| 教案生成与写作 | HTTPX、兼容 OpenAI Chat Completions 的配置端点 | 空白或模板生成与编辑器写作共用授权资料页提取。提供方与模型从环境配置读取。 |
| 教师 Agent | LangChain Deep Agents、LangChain OpenAI 适配器、Skills | 可选安装。现有工具按教师和课程读取资料、目录、逐页正文与教案。 |
| 验证 | Python unittest、FastAPI TestClient、Vite 生产构建、Chrome | 回归覆盖关键业务、权限和保存冲突。模型调用可用替身验证。 |

本轮验收环境使用 Python 3.12.14、Node.js 25.9.0、LibreOffice 26.8.2.2。前端锁文件包含 Vue 3.5.45、Vue Router 4.6.4、Vite 7.3.8、Lucide Vue 0.548.0。后端本机安装包含 FastAPI 0.162.4、Pydantic 2.14.3、Uvicorn 0.54.0、SQLAlchemy 2.0.57、pypdf 7.0.1、python-docx 1.2.0、python-pptx 1.0.2、ReportLab 4.5.1、Deep Agents 0.7.35 和 langchain-openai 1.7.4。后端版本范围见依赖文件。

## 选型记录

| 日期 | 组件 | 决策与理由 |
| --- | --- | --- |
| 2026-11-11 | 平台框架 | 用户确认 Vue、FastAPI 和 Deep Agents。业务页面与工具复用后端服务，学校管理端独立部署入口。 |
| 2026-11-12 | 首版资料处理 | 选择 LibreOffice 固定 Office 分页，pypdf 提取 PDF 书签与正文，PDF.js 负责统一预览。目录与教案选页使用同一页码。扫描件 OCR 留待独立评估。 |
| 2026-11-12 | 首版教案编辑 | 采用 Tiptap 验证结构化草稿和光标续写。分页模板编辑获批后迁入直接读写 DOCX 的编辑器。 |
| 2026-11-12 | Word 分页编辑和模板 | 用户确认采用 DOCX Editor 的 Vue 与 Core 包。采用 Apache-2.0 的分页、编辑与保存能力，复用现有 LibreOffice 处理 DOC 与 PDF。在隔离环境中验证学校旧版 Word 模板转换、浏览器 4 页展示、表格编辑保存和导出页数。 |
| 2026-11-12 | Word 模板 AI 填充 | 使用现有模型的 JSON 响应按栏目输出，python-docx 按 `{{栏目名}}`、已知标题说明和相邻空白单元格定位写入，保留已有布局。未识别到教学栏目时在模板末尾追加生成内容。 |
| 2026-11-13 | 模型服务配置验证 | 超算互联网 Token Plan 的 `DeepSeek-V4.1-Flash-1017-Event` 复用现有 OpenAI Chat Completions 接口。使用套餐专属密钥，修改 `.env` 后重启后端。验证了模型列表、教案生成、写作和 Agent 工具调用。 |
| 2026-11-13 | 教师思维导图和模板 | 用户确认 Vue 3 接入 MIT 许可的 `simple-mind-map` 0.14.0-fix.3，按路由加载。相比 AntV X6，直接复用主题编辑、布局、拖拽和图片导出。FastAPI、SQLAlchemy 和现有模型接口处理版本、资料授权及结构化生成。内置教育模板使用版本化 JSON，个人模板独立保存。 |

中文字体和复杂对象可能影响分页。新增学校模板时可用原件对照在线编辑和 PDF 导出。[Vue 组合接口](https://www.docx-editor.dev/docs/2.x/vue/composition) · [DOCX 格式兼容](https://www.docx-editor.dev/docs/2.x/docx-fidelity) · [LibreOffice 转换格式](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html)

教案使用 Vue 适配器原生的 `DocxEditorToolbar.ImageInsert`，随格式工具栏适配屏幕宽度。编辑器校验 PNG、JPEG 和 GIF，并将图片嵌入 DOCX。保存、预览与导出使用同一教案文档。[图片插入与兼容格式](https://www.docx-editor.dev/docs/2.x/guides/images) · [原生工具栏](https://www.docx-editor.dev/docs/2.x/guides/toolbar)

教案使用 `TableInsert` 插入原生表格。模型返回的 Markdown 管道表格由后端解析为段落和表格，整篇生成由 python-docx 写入，光标建议采纳时由 DOCX Editor 通过富文本粘贴写入。候选在编辑器画布内定位显示，未采纳的内容不进入文档。中文字体目录通过 `supportedFamilies` 配置，HarfBuzz WASM 随应用提供。预览与导出分别依赖客户端与转换服务器可用的字体。[表格和工具栏插槽](https://www.docx-editor.dev/docs/2.x/guides/chrome-slots#images-and-tables) · [字体配置](https://www.docx-editor.dev/docs/2.x/guides/fonts)

模板填充沿用目标段落的字体、字号与行距。编辑器内采纳多段文字或表格时，后端用 python-docx 生成含中文字体字段的 Word 片段，通过固定版本 DOCX Editor 的富文本粘贴写入。升级编辑器时验证片段粘贴、字体与段落格式。[DOCX 富文本粘贴与格式兼容](https://www.docx-editor.dev/docs/2.x/docx-fidelity)

空白 DOCX 和无模板生成的教案使用显式中文字体与 `zh-CN` 文档语言。归档和恢复使用状态接口更新同一教案。复制接口使用 UUID 请求键识别同一次复制的重试。

思维导图保存平台定义的纯文本节点、样式和已授权资料引用。Vue 适配器负责与绘图库交换节点数据。浏览器生成 PNG，默认按 2 倍像素密度导出，并按浏览器画布上限缩放。已在 Windows Chrome 验证中文多行输入、分支换父节点、自动保存、模板副本、来源跳页和完整图幅导出。已验证真实模型按资料页生成和 Agent 创建工具。[SimpleMindMap](https://wanglin2.github.io/mind-map-docs/start/introduction.html) · [AntV X6 导图示例](https://x6.antv.antgroup.com/en/examples/showcase/practices/mindmap/)

编辑工具扩展继续使用已选的 SimpleMindMap。关联线和外框启用库自带插件，概要、图标和链接复用节点能力。附件引用课程资料库。公式预览声明现有锁文件中的 KaTeX 0.16.47 为直接依赖，按纯 LaTeX 输入在浏览器渲染。表格、代码块和双向链接保存在节点结构中，通过编辑器查看。Windows Chrome 已验证公式预览、节点保存重开及图形导出。[SimpleMindMap 节点内容](https://wanglin2.github.io/mind-map-docs/course/course2.html) · [知犀编辑工具](https://help.zhixi.com/faq/21585.html)

### 教师试卷

2026-11-13 确认复用 Vue 3 的 DOCX Editor 2.37.0、python-docx 和 LibreOffice Writer。Word 文件以 DOCX 为在线编辑格式，DOC 导入和导出经过 LibreOffice。试卷正文及题目元数据分别保存。优先按 Word 段落和编号提出题目范围，教师确认后用 Word 书签标识题目。单题修改仅写入确认的范围，参考答案单独保存。试卷题型按作答方式建模，专业细分采用标签。生成和单题修改复用现有 Chat Completions 接口。Windows Chrome 已验证书签定位、手动选区标记、DOCX 重开、PDF 预览和旧版 DOC 导出。[DOCX Editor 书签](https://www.docx-editor.dev/docs/2.x/guides/bookmarks) · [LibreOffice 转换格式](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html) · [ACL 2025 选择题研究](https://aclanthology.org/2025.findings-acl.432/) · [EMNLP 2026 干扰项研究](https://aclanthology.org/2026.findings-emnlp.2382/)

## 待验证和待选型

- 答题卡拟延用 DOCX Editor、python-docx 和 LibreOffice，使 Word 版可调整行高和边框。LaTeX 另评估 XeLaTeX 与 `ctexart` 或 `exam-zh` 的中文排版、公式及答题区。TeX Live 2024 已通过本地最小样例编译，包含中文、分式、横线和作答框。产品接入和正式模板待确认。[CTAN exam-zh](https://ctan.org/tex-archive/macros/xetex/latex/exam-zh)

- 资料向量检索的候选为 PostgreSQL + pgvector 与 Qwen3-Embedding。以真实中文课程样本比较证据召回、章节切分与引用页码后再确认。
- 对话持久化、Agent 修改教案、耗时任务队列、数据库迁移、对象存储及生产部署需要单独验收。
- 知识框架、PPT、批改、学情分析、数字人和语音分别进入组件选型流程。

后续每个组件获批后，在本页记录日期、技术及版本、选择理由、运行条件和验证结果。依赖变更同时更新依赖文件和开发日志。
