# Dianoia 技术栈与选型记录

更新于 2026-11-19。此文档记录实际依赖、外部运行条件及尚待选型的组件。前端依赖以 `frontend/package.json` 和 `frontend/package-lock.json` 为准，后端通用依赖以 `backend/requirements.txt` 和 `backend/requirements-agent.txt` 为准，专用环境依赖与约束见对应组件记录。标记为建议或待确认的方案不表示已安装。

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

2026-11-14 确认继续使用 DOCX Editor、python-docx 和 LibreOffice。答题卡由已确认的题目按题型生成，单独保存区域设置和 DOCX，支持分页预览、在线编辑与 Word 导出。LaTeX 使用 XeLaTeX 和 `ctexart` 从结构化题目和答题卡设置排版，分别提供 `.tex` 和编译后的 PDF。验收使用 TeX Live 2024、XeTeX 0.999996、CTeX 2.5.10，部署依赖见 README。已编译验证三类文档的中文、公式、页码和作答区域。[CTAN ctex](https://ctan.org/pkg/ctex)

试卷公式编辑采用 MathLive 0.111.4 提供可视输入和数学键盘，沿用 KaTeX 0.16.47 提供实时预览。MathLive 按需加载，字体随前端提供。后端使用 latex2mathml 3.81.1 和受支持的 MathML 到 OMML 映射生成 Word 原生公式，omml2latex 0.1.1 用于读取可识别的导入公式。现有 DOCX Editor 2.37.0 通过 Flat OPC 写入公式，网页画布的公式以 KaTeX 字形排版，普通 PDF 由 LibreOffice 生成。已验证 Chrome 保存重开后的矩阵编辑、分式录入和答案预览，以及高数和线代样卷的 LibreOffice 与 XeLaTeX 导出。[MathLive 数学键盘](https://mathlive.io/mathfield/guides/virtual-keyboard/) · [Microsoft Office Math](https://learn.microsoft.com/en-us/office/math/) · [NIST 关于 LaTeX 与 MathML 表示的研究](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=925433)

### 教学演示文稿

确认分步交付。编辑器参考 PPTist 的操作布局，采用 Vue 3、Konva 10.9.1 与 vue-konva 4.0.1。应用保存可独立校验的幻灯片和对象数据，中文文本编辑使用浏览器原生输入控件。后端复用 FastAPI、SQLAlchemy、python-pptx 1.0.2 和 LibreOffice Impress，由同一份已保存数据导出可编辑 PPTX 和 PDF。Python 环境已完成文本、形状、表格、图表、讲者备注及 PDF 的最小验证。另一候选 ONLYOFFICE 适合原生 PPTX 编辑，已有母版、动画和复杂对象的往返保真另外验收。[Vue Konva](https://konvajs.org/docs/vue/index.html) · [python-pptx](https://python-pptx.readthedocs.io/en/latest/) · [PPTist](https://github.com/pipipi-pikachu/PPTist)

国内容例用于提炼教学版式，平台用原创通用模板提供授课、实验、实训、习题、案例、研讨、复习、微课等场景。AI 采用大纲与页面分阶段生成，局部生成以页或选中对象为目标，结构化候选按版本采纳。参考资料复用课程资料库的页码范围和访问校验。Agent 复用教师课件服务。[清华大学公开演示文档模板](https://www.env.tsinghua.edu.cn/info/1344/7931.htm) · [西安交通大学实验教学管理规范](https://jxjc.xjtu.edu.cn/info/1033/1129.htm) · [PPTAgent](https://aclanthology.org/2025.emnlp-main.728/) · [DECKBench](https://arxiv.org/abs/2602.13318)

Pillow `>=12.2,<14` 用于服务器端验证 PNG、JPEG 的文件格式与解码上限，本机验证版本为 13.0.0。前端构建将画布依赖放入按需加载的课件模块。运行 PDF 导出需要可执行的 LibreOffice Impress 和与课件匹配的中文字体，支持通过 `DIANOIA_SOFFICE` 指定路径。Chrome 验证模板创建、拖拽、编辑、放映和下载，PPTX 已复读验证原生文字、表格、图表和备注，PDF 已验证五页输出。整稿、局部备注、Agent 草稿及候选使用真实模型验证，资料范围传入通过固定测试材料回归。

2026-11-14 课件质量迭代沿用当前模型和 PPTX 输出链路。内置主题负责配色、封面与正文风格，模型根据内容字段选择逐页版式，渲染器负责表格、代码、步骤卡片以及字号和版面边界。参考 PPTAgent 的分阶段生成和 PresentBench 对内容与视觉布局的独立评价。外部模板候选为 SlidesCarnival CC BY 4.0，模板需要保留署名，随附照片按单独条款处理；本次使用原创主题。[Kimi Slides 创建模式](https://www.kimi.ai/help/slides/ppt-creation-mode) · [Gamma 主题与视觉素材](https://help.gamma.app/en/articles/11856101-how-do-i-use-the-visuals-menu-in-gamma) · [PPTAgent](https://aclanthology.org/2025.emnlp-main.728/) · [PresentBench](https://presentbench.github.io/) · [SlidesCarnival 条款](https://www.slidescarnival.com/terms-of-use/)

课件公式复用试卷的 MathLive 0.111.4、KaTeX 0.16.47、latex2mathml 3.81.1 和 LaTeX 校验。浏览器采用公式字形排版，PPTX 写入 DrawingML 中的 Office Math。已用最小样例确认 LibreOffice Impress 可将分式和矩阵输出到 PDF。备选 MathJax SVG 可固定显示，但需要另行验证 PowerPoint 原生编辑体验。[Microsoft DrawingML 公式规范](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/cdafda97-9124-48ed-8d64-7f1dd9197c8a) · [MathJax SVG](https://docs.mathjax.org/en/latest/output/index.html)

### 2026-11-15｜课件模板库、编辑器与数据图表

沿用已选 Vue 3、Konva 10.9.1、vue-konva 4.0.1、FastAPI、Pydantic 与 python-pptx 1.0.2。模板按需读取完整页序，样式来自平台的可编辑对象。Kimi 用于对照通用视觉主题，清华大学和 MIT Sloan 的教学或品牌模板用于参考课程结构、投影与录课构图。PPTist 提供形状、图表和放映入口的交互参考。候选方案包括直接嵌入 PPTist、采用 ECharts 和使用在线设计平台。延续现有画布使在线数据、保存和从同一模型导出原生 PPTX 的行为可独立验证。将学校演示资料作为设计参考，应用内模板采用原创版式和素材。[Kimi Slides](https://www.kimi.ai/academy/slides-intro) · [清华大学](https://www.env.tsinghua.edu.cn/info/1344/7931.htm) · [MIT Sloan](https://mitsloanedtech.mit.edu/studio/download-a-template/) · [PPTist](https://github.com/pipipi-pikachu/PPTist)

参照 Doc2Chart 和 VisEval，把图表意图、来源数据与绘制分开。AI 返回结构化图表请求，服务端核对类别和数值有来源，Konva 和 python-pptx 渲染同一份数据。手动或明确启用的演示数据须可识别。核验重点包括数据值、图形种类、页内来源、可编辑工作簿和 PDF 可见性。[Doc2Chart](https://aclanthology.org/2025.emnlp-main.1770/) · [VisEval](https://arxiv.org/abs/2407.00981)

沿用现有部署依赖。Chrome 验证模板末页预览、折线和散点编辑流程、形状与放映。python-pptx 复读八种原生图表、坐标和数值，LibreOffice Impress 验证八页图表 PDF。真实模型按教师给定的三项读数生成英文折线图，保存并导出。

### 2026-11-15｜演示文稿音视频与对象级动画

首版范围已确认。音视频支持教师上传 MP4（H.264，包含音轨时要求 AAC）和 MP3。媒体字节存放在数据目录，数据库维护课程、上传者和文件信息，课件保存媒体引用。浏览器使用原生播放控件和 Starlette FileResponse 的范围请求。与外链播放相比，嵌入模式支持教室离线放映，PPTX 使用 python-pptx 1.0.2 和 Office Open XML 媒体关系，PDF 保留静态媒体标记。自定义模板可以跨课程复用，保存模板时移除课程媒体与其引用。[Microsoft 媒体格式](https://support.microsoft.com/en-us/powerpoint/video-and-audio-file-formats-supported-in-powerpoint) · [Starlette 响应](https://starlette.dev/responses/) · [python-pptx 媒体结构](https://python-pptx.readthedocs.io/en/latest/dev/analysis/shp-movie.html)

服务器通过 ffprobe 检查实际容器和编解码器，避免依赖扩展名和浏览器上报的 MIME。部署使用 PATH 中的 ffprobe 或通过 `DIANOIA_FFPROBE` 指定路径，本机版本为 7.0.2。只对本地上传暂存文件进行探测，限制探测时间，保留原始字节用于下载和嵌入。[ffprobe 官方文档](https://ffmpeg.org/ffprobe.html)

每页保存有序动画序列，支持淡入、飞入、强调和淡出，支持点击与上一动画结束后触发。网页放映复用现有 Konva 画布和公式、媒体覆盖层，由同一序列推进。PPTX 使用原生时序。PDF 输出静态全页供印刷。验收覆盖网页点击推进、返回重放、媒体播放及拖动进度，以及 PowerPoint 和 WPS 的播放兼容性。课件中使用动画以分步展示和强调为主。[PowerPoint 时序结构](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.timing) · [多媒体学习元分析](https://doi.org/10.1016/j.edurev.2025.100730)

已在 Chrome 验证上传、媒体播放和定位进度、动画执行及重新进入页面。PowerPoint 16 和 WPS 12 复读了导出文件中的音频、视频、动画类型与触发方式。LibreOffice 导出的 PDF 已核对媒体标记。单个媒体上限 32 MB，单份课件按不同媒体文件计总量上限 96 MB。

### 2026-11-15｜网页对象动画播放

参考 PPTist 对目标对象直接施加效果、完成后推进队列的思路。Dianoia 在 Vue 3、Konva 10.9.1 和 vue-konva 4.0.1 上使用浏览器 `requestAnimationFrame` 计算进度，通过 Konva 批量绘制和 CSS 自定义属性更新对象。预览和网页放映共用队列与效果计算。系统开启减少动态效果时，飞入和缩放强调使用透明度变化。前端依赖及课件动画数据格式沿用原有版本。[PPTist 对象预览](https://github.com/pipipi-pikachu/PPTist/blob/6907580cce33914a4c58be03e13ac0c332d8b5e9/src/views/Editor/Toolbar/ElementAnimationPanel.vue) · [PPTist 放映调度](https://github.com/pipipi-pikachu/PPTist/blob/6907580cce33914a4c58be03e13ac0c332d8b5e9/src/views/Screen/hooks/useExecPlay.ts)

### 2026-11-16｜数字课程首版

按教师确认的 InfiniteTalk 路线开发。教师上传 PPT/PPTX，逐页审阅和编辑口播稿，选择形象和音色后提交生产，在项目内查看进度并导出 MP4。工作流参考讯飞智作。使用 InfiniteTalk 官方单人 image-to-video CLI 的 480P 流式模式，根据人物照片和合成音频生成说话画面。论文分别讨论了流式生成、唇形同步和长序列一致性。Kokoro 可提供预置语音，教师音频样本的零样本克隆需要另外的语音模型。CosyVoice 可作为候选，首版通过本地命令协议接入部署选择的语音合成器。网页端复用 Vue、FastAPI、现有模型接口和 SQLAlchemy 持久化任务，由独立 worker 调用 LibreOffice、Poppler、FFmpeg 和 GPU 推理环境。监听任务进度采用短轮询。[讯飞智作](https://peiyin.xunfei.cn/seospread/ai13/index.html) · [InfiniteTalk 源码](https://github.com/MeiGen-AI/InfiniteTalk) · [InfiniteTalk 论文](https://arxiv.org/abs/2508.14033) · [CosyVoice 接口示例](https://github.com/FunAudioLLM/CosyVoice/blob/main/example.py)

预置音色使用 Kokoro 82M v1.1-zh 的普通话女声和男声，推理在独立 Python 环境运行。APIs 与 worker 共用数据库及素材目录。课件按页导出静态画面，右侧合成数字讲师，输出 1280×720 H.264/AAC。验收环境使用 FFmpeg 7.0.2 和 Poppler 26.07.0。安装变量、语音合成协议和首版限制记录在[数字课程部署说明](digital-courses.md)。[Kokoro 模型卡](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)

### 数字课程声音档案与逐页试音

沿用 InfiniteTalk 官方单人推理和现有 WAV 语音合成协议。参考官方示例，`cond_audio.person1` 是待驱动嘴型的整段口播音频。参考样本先由独立 TTS 使用。教师以声音档案管理多条各自带原文的样本，可标记一条用于合成。采用浏览器 MediaRecorder 录音并由现有 FFmpeg 统一转为 16 kHz 单声道 PCM。试音和正式生产复用同一套语音驱动。编辑器参考讯飞智作的课件缩略图、中央画布及右侧素材选取布局。[InfiniteTalk 官方示例](https://raw.githubusercontent.com/MeiGen-AI/InfiniteTalk/main/examples/single_example_image.json) · [讯飞智作](https://peiyin.xunfei.cn/seospread/ai13/index.html)

预置音色已在本机 Kokoro 0.9.4、misaki 0.9.4 与 PyTorch 2.6.0 CPU 环境验证。新增 InfiniteTalk 单人 FP8 配置及权重下载命令，保留官方全精度参数。下载工具在独立模型环境使用 huggingface_hub，无需改动 FastAPI 应用依赖。部署前需用实际模型完成短片口型、声音与导出验收。[InfiniteTalk 量化推理](https://github.com/MeiGen-AI/InfiniteTalk#3-run-with-the-quantization-model-only-support-run-with-single-gpu)

### 2026-11-19｜数字课程切换至 SadTalker

按项目负责人确认，数字课程的照片驱动改用 SadTalker 512 人脸模型。它根据语音预测表情和头部运动，再把动画脸合成进原照片。比较了 InfiniteTalk 的低显存卸载和 MuseTalk 的局部口型替换。Dianoia 当前主要使用静态讲师照片和课件旁置画面，SadTalker 的完整照片模式对应这一输入形态，单档推理权重约 1.18 GB。正在验证本机 RTX 4070 SUPER 的真实渲染。讲稿、Kokoro 预置语音、可配置的个人语音合成器、SQLAlchemy 任务及 FFmpeg 合成环节继续使用现有接口。[SadTalker 论文](https://openaccess.thecvf.com/content/CVPR2023/html/Zhang_SadTalker_Learning_Realistic_3D_Motion_Coefficients_for_Stylized_Audio-Driven_Single_CVPR_2023_paper.html) · [官方权重](https://github.com/OpenTalker/SadTalker/releases/expanded_assets/v0.0.2-rc)

实际采用官方源码版本 `cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8`，独立 Python 3.12、PyTorch 2.6.0 + CUDA 12.4、torchvision 0.21.0，配套版本在 `backend/requirements-sadtalker.txt`。应用启动脚本适配上游使用的旧 NumPy 别名、二维平移数组及 torchvision 导入，并调用配置的 FFmpeg。渲染默认使用 512、full、still、batch_size=1，每段最长 12 秒。两页真实验收输出 23.701 秒的 H.264/AAC 720p 视频，耗时 244 秒。RTX 4070 SUPER 测试期间总显存峰值 6966 MiB，测试前桌面占用 1170 MiB。视频轨与音频轨相差约 16 毫秒，下载与范围请求通过。正式长课程的段间过渡及不同照片仍需业务验收。个人音色克隆通过独立 TTS 驱动配置。

### 2026-11-19｜个人音色零样本 TTS 配置

按项目负责人本轮配置要求，落实已有 CosyVoice 驱动，采用 CosyVoice2-0.5B 的 `inference_zero_shot` 接口：输入一条参考音频、准确原文及目标讲稿，输出 24 kHz PCM WAV，再供 SadTalker 使用。声音档案保留多条样本，每次选用标记的参考样本，无需教师训练模型。官方 Kokoro 音色继续使用原有环境。相较另建 GPT-SoVITS 训练流程，此方案可直接接入已有任务快照和 WAV 协议；CosyVoice 3 是后续质量对比候选。本轮优先验证已预留的 CosyVoice 2 路径。[官方零样本示例](https://github.com/FunAudioLLM/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/example.py) · [CosyVoice 2 论文](https://arxiv.org/abs/2412.10117)

推理使用独立 Python 3.12 环境，源码固定 `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`，Matcha-TTS 子模块固定 `dd9105b34bf2be2230f4aa1e4769fb586a3c824e`，模型固定 Hugging Face `FunAudioLLM/CosyVoice2-0.5B` 修订 `eec1ae6c79877dbd9379285cf8789c9e0879293d`。采用 PyTorch / torchaudio 2.6.0 + CUDA 12.4、transformers 4.51.3、ONNX Runtime 1.18.0、NumPy 1.26.4 和自带规范化资源的 WeText 0.2.1。固定 NumPy、SciPy 和 contourpy 版本，防止绘图等间接依赖升级破坏语音推理的二进制兼容性。配套依赖及完整验收环境约束分别记录在 `backend/requirements-cosyvoice.txt` 与 `backend/constraints-cosyvoice.txt`。本机已通过 CUDA 导入、依赖一致性及中文数字/英文数字规范化检查。[WeText 官方实现](https://github.com/pengzhendong/wetext)

真实模型已完成验收。使用平台合成的测试参考录音及准确原文，独立 CLI 输出不同内容的 5.44 秒、24 kHz PCM16 单声道 WAV，冷启动含模型加载耗时 28.2 秒，GPU 总显存峰值 5792 MiB（桌面基线 1408 MiB）。通过常规声音档案、样本上传、指定参考和试音 API 再次输出 5.6 秒音频，耗时 20.7 秒；排队后删除原参考样本，任务仍通过快照成功。个人音色经 SadTalker 生成 5.621 秒 720p H.264/AAC 视频，耗时 125.5 秒，验证下载、范围请求、音画轨时长及人物帧变化，查看了合成画面。教师真实录音的相似度、不同录音环境和长讲稿效果需在业务使用时继续验收。

### 2026-11-19｜在线题库设计建议（待技术确认，未开发）

负责人确认采用自主练习，聚焦题库、参考答案与发布，不涉及成绩。产品设计、章节/子章节、默认和上传封面、AI 与 Word 导入、发布版本、Agent 草稿工具及学生端接入条件见[在线题库设计 v0.1](online-question-bank-design.md)。当前学生名册尚无登录账号关联，认证仅接受教师/管理员；学生作答仍按既有约定在教师端之后开发，不把教师发布管理视为已完成学生答题。

建议沿用 Vue 3、FastAPI、Pydantic、SQLAlchemy 与现有模型调用，新增独立的结构化题目 Schema，不复用试卷分值或 DOCX 作为在线正文。富文本候选基线为 Tiptap 3.34.0 的 MIT 开源核心及同版本 Vue/StarterKit/图片/表格扩展；2026-11-19 核对官方 npm 元数据，尚未安装。复用 MathLive 0.111.4 和 KaTeX 0.16.47，通过公式节点保存可再编辑的 LaTeX。相比继续使用 Word 分页编辑，结构化 JSON 更适合单题、选项、答案及手机阅读；相比部署完整 Moodle，更易复用现有课程、资料和 Agent 服务。[Tiptap Vue 3](https://tiptap.dev/docs/editor/getting-started/install/vue3) · [JSON 持久化](https://tiptap.dev/docs/editor/core-concepts/persistence) · [Moodle 题库](https://docs.moodle.org/501/en/Question_bank)

图片使用现有 Pillow 和私有资源引用，默认封面采用受控原创模板。正式部署采用现有 PostgreSQL 路线，建议以 Alembic 1.20.1 建立数据库基线及本模块新表迁移；该版本已核对 PyPI，未安装或运行迁移。AI 耗时任务沿用数据库任务、租约及心跳的模式，题库 worker 与 GPU 课程生产隔离。发布使用不可变题目版本与事务快照，学生读取按课程/班级和发布版本授权。技术获批后先验证编辑器、中文输入、公式、表格、图片和 JSON 保存重开，再安装并锁定依赖。

生成质量参考 2026 年 SagE-QG 对阅读理解技能与证据关联的研究，以及 2025 年高校形成性练习与反馈研究。产品采用按知识点及资料范围生成、记录来源、教师确认后发布的流程；这不代表已验证所有学科的正确率或本平台的学习效果。[SagE-QG](https://aclanthology.org/2026.findings-emnlp.424/) · [高校形成性练习与反馈](https://aclanthology.org/2025.aimecon-main.36/)

## 待验证和待选型

- 资料向量检索的候选为 PostgreSQL + pgvector 与 Qwen3-Embedding。以真实中文课程样本比较证据召回、章节切分与引用页码后再确认。
- 对话持久化、Agent 修改教案、耗时任务队列、数据库迁移、对象存储及生产部署需要单独验收。
- 知识框架、批改、学情分析及数字课程后续能力分别进入组件选型流程。

后续每个组件获批后，在本页记录日期、技术及版本、选择理由、运行条件和验证结果。依赖变更同时更新依赖文件和开发日志。
