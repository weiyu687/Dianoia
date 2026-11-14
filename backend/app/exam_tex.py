import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException

from .exam_math import formulas, valid_latex
from .exam_sheet import OBJECTIVE, OPTION_LABELS, blank_rows, selection_labels, sheet_groups

ESCAPES = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "%": r"\%",
    "&": r"\&", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
PREAMBLE = r"""\documentclass[UTF8,a4paper,11pt,fontset=fandol]{ctexart}
\usepackage[left=23mm,right=23mm,top=21mm,bottom=20mm]{geometry}
\usepackage{amsmath,amssymb,fancyhdr,lastpage,needspace}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyfoot[C]{第 \thepage\ 页\quad 共 \pageref{LastPage}\ 页}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\setlength{\emergencystretch}{2em}
\ctexset{section={format=\raggedright\bfseries\large,beforeskip=10pt,afterskip=5pt}}
\newcommand{\checksquare}{\fbox{\rule{0pt}{1.3mm}\rule{1.3mm}{0pt}}}
\providecommand{\degree}{^{\circ}}
\begin{document}
"""


def escape(value):
    return "".join(ESCAPES.get(char, char) for char in str(value)
                   if char in "\n\t" or ord(char) >= 32)


def text(value):
    return "".join(
        (r"\[" + latex + r"\]" if display else r"\(" + latex + r"\)")
        if latex and valid_latex(latex) else escape(original).replace("\n", "\n\\par\n")
        for original, latex, display in formulas(value)
    )


def sheet_content(question, area):
    label = escape(question.label)
    if question.kind in OBJECTIVE:
        return [label + r"\quad " + r"\qquad ".join(f"［{item}］" for item in selection_labels(question, area))]
    if question.kind == "blank":
        rows = [label + r"\quad "]
        for index in range(area.blanks):
            if index and index % blank_rows(area) == 0:
                rows.append(r"\hspace*{8mm}")
            if area.blanks > 1:
                rows[-1] += f" ({index + 1}) "
            rule = (rf"\rule{{{area.blank_mm}mm}}{{0.4pt}}" if area.style != "blank"
                    else rf"\hspace*{{{area.blank_mm}mm}}")
            rows[-1] += rule
        return [row + r"\par" for row in rows]
    line = area.line_mm
    width = area.width_mm
    if area.style == "ruled":
        return [rf"\Needspace{{{line + 8}mm}}{label}\par",
                *[rf"\vbox to {line}mm{{\vfil\hbox{{\rule{{{width}mm}}{{0.4pt}}}}}}" for _ in range(area.lines)]]
    rows = [rf"\Needspace{{{min(line * area.lines, 216) + 8}mm}}{label}\par"]
    block = 216 // line
    for start in range(0, area.lines, block):
        height = min(block, area.lines - start) * line
        box = rf"\rule{{0pt}}{{{height}mm}}\rule{{{width - 3}mm}}{{0pt}}"
        rows.append(rf"\noindent\fbox{{{box}}}\par" if area.style == "boxed" else rf"\noindent\hbox{{{box}}}\par")
    return rows


def exam_tex(fields, questions, variant, areas=None):
    suffix = {"paper": "试卷", "answers": "参考答案", "sheet": "答题卡"}[variant]
    title = escape(f"{fields['school']}期末考试{suffix}")
    lines = [PREAMBLE, r"\begin{center}", rf"{{\Large\bfseries {title}}}\par",
             rf"{{\large {escape(fields['title'])}}}", r"\end{center}", r"\begin{tabular}{@{}p{85mm}p{78mm}@{}}"]
    metadata = [
        ("课程名称", fields["course"], "学年学期", fields["term"]),
        ("任课教师", fields["teacher"], "教学班", fields["class_name"]),
    ]
    for label, value, right, other in metadata:
        left_text = escape(value) or r"\hrulefill"
        right_text = escape(other) or r"\hrulefill"
        lines.append(rf"\textbf{{{label}}}\quad {left_text} & \textbf{{{right}}}\quad {right_text} \\[1ex]")
    if variant != "answers":
        lines.append(r"\textbf{姓　名}\quad \hrulefill & \textbf{学　号}\quad \hrulefill \\[1ex]")
        lines.append(r"\textbf{考试方式}\quad \checksquare{} 闭卷\quad \checksquare{} 开卷 & "
                     r"\textbf{卷　别}\quad \checksquare{} A 卷\quad \checksquare{} B 卷 \\[1ex]")
    lines.append(r"\end{tabular}\par")
    groups = list(sheet_groups(questions))
    if variant == "paper":
        totals = sum(q.points or 0 for q in questions)
        columns = len(groups) + 2
        lines.extend([rf"\begin{{center}}考试时长\quad\rule{{12mm}}{{0.4pt}} 分钟\qquad 卷面总分 {totals} 分\par",
                      rf"\begin{{tabular}}{{|*{{{columns}}}{{c|}}}}\hline",
                      " & ".join(["题号", *[label.split("、", 1)[0] for label, _ in groups], "总分"]) + r"\\\hline",
                      " & ".join(["得分", *[r"\rule{6mm}{0pt}" for _ in range(columns - 1)]]) + r"\\\hline",
                      r"\end{tabular}\end{center}", "考生须知：请填写姓名、学号和教学班，按题号顺序作答。"])
    elif variant == "sheet":
        lines.append("作答须知：请按题号在对应区域内作答。")
    for label, items in groups:
        lines.append(rf"\section*{{{escape(label)}}}")
        if variant == "paper":
            lines.extend([r"\hfill\begin{tabular}{|c|p{16mm}|}\hline",
                          r"得分 & \\ \hline 评分人 & \\ \hline\end{tabular}\par"])
        for q in items:
            if variant == "sheet":
                lines.extend(sheet_content(q, areas[q.id]))
                continue
            points = f"（{q.points}分）" if q.points is not None else ""
            lines.append(rf"{escape(q.label)}\quad {text(q.stem)}{points}\par")
            if variant == "paper":
                for option, letter in zip(q.options, OPTION_LABELS):
                    lines.append(rf"\hspace*{{5mm}}{letter}.\quad {text(option)}\par")
            else:
                lines.append(rf"\textbf{{参考答案}}\quad {text(q.answer or '待补充')}\par")
                if q.explanation:
                    lines.append(rf"\textbf{{评分要点}}\quad {text(q.explanation)}\par")
    return ("\n".join([*lines, r"\end{document}", ""])).encode("utf-8")


def xelatex_pdf(content):
    if len(content) > 512 * 1024:
        raise HTTPException(422, "LaTeX 源文件较大，请下载源文件在本地编译")
    executable = shutil.which(os.getenv("DIANOIA_XELATEX", "").strip() or "xelatex")
    if not executable:
        raise HTTPException(503, "LaTeX PDF 需要安装 XeLaTeX 并配置 DIANOIA_XELATEX")
    with TemporaryDirectory(prefix="dianoia-tex-") as tmp:
        folder = Path(tmp)
        (folder / "exam.tex").write_bytes(content)
        # Only source produced by exam_tex reaches the compiler.
        environment = dict(os.environ, openin_any="p", openout_any="p", TEXMFOUTPUT=tmp)
        command = [executable, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "exam.tex"]
        try:
            for _ in range(2):
                subprocess.run(command, cwd=folder, env=environment, check=True, timeout=25,
                               capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return (folder / "exam.pdf").read_bytes()
        except subprocess.TimeoutExpired as error:
            raise HTTPException(504, "LaTeX 编译超时，可先下载源文件") from error
        except (subprocess.CalledProcessError, OSError) as error:
            raise HTTPException(422, "LaTeX 编译失败，请检查中文宏包或题目中的公式语法") from error
