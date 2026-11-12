# Dianoia 智能教育平台

教师端和学校管理端由两个独立的 Vue 应用入口提供服务，共用 FastAPI 和数据库。开发环境支持 Python 3.12 与 Node.js 22.12 及以上版本。

依赖、运行条件和变更依据见[技术栈与选型记录](docs/technology-stack.md)。

## 本地运行

在仓库根目录安装 Python 依赖。Windows PowerShell 示例使用下列命令。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m app.seed
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

初始化命令提示输入本机虚拟账号的密码，默认创建教师 `teacher`、管理员 `admin` 和示例课程。若要验证独立 Agent，对应的安装文件是 `backend/requirements-agent.txt`。

在另一个终端从仓库根目录启动前端。

```powershell
Set-Location frontend
npm ci
npm run dev
```

- 教师端进入 [本地工作台](http://127.0.0.1:5173/)，资料库右上角可上传，教案页可新建、检索、重命名、复制、归档和删除。
- 学校管理端从 [独立管理入口](http://127.0.0.1:5173/admin/) 登录，可下载 XLSX 模板、预检、确认导入及开通教师账号。
- 从「教案 → 模板管理」上传、预览、重命名或删除 Word 模板。新建时可以选模板、创建空白文档或按资料生成草稿。教案在网页中分页编辑，以 PDF 预览，可导出 DOCX、DOC 或 PDF。
- 教案正文中按 `Alt+\` 打开续写，`Tab` 采纳，`Esc` 取消。选择正文后可从工具栏重写选区。

## 配置

将 `backend/.env.example` 复制到 `backend/.env`，按需要填写。配置文件和本机数据由 Git 忽略。

| 变量 | 用途 |
| --- | --- |
| `DIANOIA_DATABASE_URL` | 本机默认 SQLite。PostgreSQL 使用 `postgresql+psycopg://…` |
| `DIANOIA_DATA_DIR` | 私有资料目录，默认 `backend/data` |
| `DIANOIA_SECURE_COOKIE` | HTTPS 部署时设为 `true` |
| `DIANOIA_MODEL_BASE_URL` | 兼容 OpenAI Chat Completions 的 API 基础地址，通常以 `/v1` 结尾 |
| `DIANOIA_MODEL_NAME` 和 `DIANOIA_MODEL_API_KEY` | 内容生成模型和服务凭据 |
| `DIANOIA_AGENT_MODEL_NAME` | 可选，指定支持工具调用的 Agent 模型 |
| `DIANOIA_SOFFICE` | LibreOffice 可执行文件路径，用于 Word、PPTX 和教案的 PDF 预览，以及旧 DOC 模板转换和 DOC 导出 |
| `DIANOIA_PDF_FONT` | 可选，旧教案 PDF 使用的中文 TrueType 字体路径 |

Word 资料上传需要 LibreOffice Writer。系统会查找 PATH、Windows 默认安装目录及数据目录下的 `tools/LibreOffice/program`，也可以通过 `DIANOIA_SOFFICE` 指定可执行文件。Word 统一转换为 PDF 后预览、读取书签和逐页提取正文。重新打开此前仅保存了文本的 Word 资料时，系统会用原件补做转换，保留原资料记录。

现有根目录 `.env` 中的 `MODEL_API_URL`、`MODEL_NAME` 和 `MODEL_API_KEY` 也可继续使用。优先采用对应的 `DIANOIA_*` 配置。

生产部署应让前端与 `/api` 同源，并用 TLS、私有持久卷和 PostgreSQL。当前迭代先验证单校工作流，部署前需要完成数据库迁移、备份、文件处理隔离和学校真实账号接入。

## 验证

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

前端在 `frontend` 目录执行 `npm run build`。测试使用虚拟教学数据与替身模型响应。实际模型调用需配置学校认可的服务端点。资料向量检索、模板自动字段填充和 Agent 写入教案属于后续迭代。
