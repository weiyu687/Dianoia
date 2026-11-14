import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from copy import deepcopy
from functools import lru_cache
from xml.etree import ElementTree

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run
from latex2mathml import exceptions as latex_errors
from latex2mathml.converter import convert
from lxml import etree
from omml2latex import convert_omml

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
SOURCE = "{urn:dianoia:math}latex"
PROJECTION = "{urn:dianoia:math}projection"
SOURCE_PREFIX = "DianoiaMath_"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
FORMULA = re.compile(
    r"(?<!\\)\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\$])\$([^\r\n$]+?)(?<!\\)\$(?!\$)",
    re.S,
)
ENVIRONMENTS = set("matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix aligned gathered cases array smallmatrix".split())
# The same input can reach XeLaTeX. Only math commands shared by the authoring and print paths belong here.
COMMANDS = set((
    "frac dfrac tfrac sqrt cdot times div pm mp le leq ge geq ne neq approx equiv sim simeq cong propto "
    "sum prod coprod int iint iiint oint lim limsup liminf infty left right middle big Big bigg Bigg "
    "sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln exp min max inf sup det gcd ker dim "
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi "
    "rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma "
    "Upsilon Phi Psi Omega in notin ni cup cap setminus subset subseteq supset supseteq emptyset varnothing "
    "to rightarrow longrightarrow leftarrow Rightarrow Leftarrow Leftrightarrow leftrightarrow mapsto "
    "uparrow downarrow forall exists neg land lor partial nabla mathrm mathbf mathit mathsf mathtt mathcal "
    "mathbb mathfrak boldsymbol text operatorname overline underline bar vec hat widehat tilde widetilde "
    "dot ddot overrightarrow angle triangle circ perp parallel vert Vert lvert rvert lVert rVert langle "
    "rangle lbrace rbrace ldots cdots vdots ddots quad qquad colon degree binom dbinom tbinom boxed "
    "overbrace underbrace overset underset limits nolimits displaystyle textstyle scriptstyle "
    "begin end"
).split())
TOKENS = re.compile(r"\\([A-Za-z]+|[\\,;:! {}|%#_$&])")
PARSER_ERRORS = tuple(value for value in vars(latex_errors).values()
                      if isinstance(value, type) and issubclass(value, Exception))


def formulas(value):
    start = 0
    for match in FORMULA.finditer(value):
        if start < match.start():
            yield value[start:match.start()], None, False
        index = next(i for i, content in enumerate(match.groups()) if content is not None)
        yield match[0], match[index + 1].strip(), index < 2
        start = match.end()
    if start < len(value):
        yield value[start:], None, False


def valid_latex(value):
    if not value or len(value) > 1600 or "^^" in value:
        return False
    if any(ord(char) < 32 and char not in "\t\r\n" for char in value):
        return False
    for token in TOKENS.finditer(value):
        name = token[1]
        if name.isalpha() and name not in COMMANDS:
            return False
    # Escaped symbols were already consumed above. Reject comments, math toggles and raw control tokens.
    plain = TOKENS.sub("", value)
    if re.search(r"[\\%$#\u2028\u2029]", plain):
        return False
    depth = 0
    for char in plain:
        depth += (char == "{") - (char == "}")
        if not 0 <= depth <= 20:
            return False
    if depth:
        return False
    environments = []
    for match in re.finditer(r"\\(begin|end)\s*\{([^{}]+)\}", value):
        name = match[2]
        if name not in ENVIRONMENTS:
            return False
        if match[1] == "begin":
            environments.append(name)
        elif not environments or environments.pop() != name:
            return False
    return not environments and len(re.findall(r"\\(?:begin|end)\b", value)) == len(
        re.findall(r"\\(?:begin|end)\s*\{[^{}]+\}", value),
    )


def element(name, *children, value=None):
    node = OxmlElement(f"m:{name}")
    node.extend(children)
    if value is not None:
        node.set(qn("m:val"), value)
    return node


def kind(node):
    return node.tag.rsplit("}", 1)[-1]


def word_run(text, upright=False):
    node = element("t")
    node.text = text
    if text != text.strip():
        node.set(qn("xml:space"), "preserve")
    return element("r", element("rPr", element("sty", value="p")) if upright else element("rPr"), node)


NARY = frozenset("∫∬∭∮∯∰∑∏∐⋃⋂")
SCRIPTS = {"msup": ("sSup", ("e", "sup")), "msub": ("sSub", ("e", "sub")),
           "msubsup": ("sSubSup", ("e", "sub", "sup"))}


def sequence(nodes):
    nodes = list(nodes)
    if nodes and kind(nodes[0]) == "mo" and nodes[0].get("fence") == "true":
        left = nodes.pop(0).text or ""
        right = ""
        if nodes and nodes[-1].get("fence") == "true":
            right = nodes.pop().text or ""
        return [delimiter(left, right, sequence(nodes))]
    result = []
    index = 0
    while index < len(nodes):
        node = nodes[index]
        if (index + 2 < len(nodes) and kind(nodes[index + 1]) == "mtable"
                and kind(node) == kind(nodes[index + 2]) == "mo"
                and (node.text, nodes[index + 2].text) in {("(", ")"), ("[", "]"), ("{", "}"), ("|", "|"), ("‖", "‖")}):
            result.append(delimiter(node.text, nodes[index + 2].text, project(nodes[index + 1])))
            index += 3
            continue
        result.extend(project(node))
        index += 1
    combined = []
    for node in result:
        if combined and combined[-1].tag == qn("m:nary") and len(combined[-1][-1]) == 0 and node.tag != qn("m:nary"):
            combined[-1][-1].append(node)
        else:
            combined.append(node)
    return combined


def delimiter(left, right, content):
    return element("d", element("dPr", element("begChr", value=left or ""), element("endChr", value=right or "")),
                   element("e", *content))


def project(node):
    tag = kind(node)
    if tag in {"math", "mrow", "mstyle", "mtd"}:
        return sequence(node)
    if tag in {"mi", "mn", "mo", "mtext"}:
        value = node.text or ""
        if re.search(r"\\[A-Za-z]", value) and tag != "mtext":
            raise ValueError("Unrecognized math command")
        return [word_run(value, tag != "mi" or len(value) > 1 or node.get("mathvariant") == "normal")]
    if tag == "mspace":
        if node.get("linebreak"):
            raise ValueError("Unsupported line break")
        return [word_run("\u2009")] if node.get("width", "0") != "0" else []
    if tag == "mfrac":
        props = [element("fPr", element("type", value="noBar"))] if node.get("linethickness") in {"0", "0pt"} else []
        return [element("f", *props, element("num", *project(node[0])), element("den", *project(node[1])))]
    if tag in {"msqrt", "mroot"}:
        degree = project(node[1]) if tag == "mroot" else []
        radicand = project(node[0]) if degree else sequence(node)
        return [element("rad", element("radPr", element("degHide", value="off" if degree else "on")),
                        element("deg", *degree), element("e", *radicand))]
    if tag in SCRIPTS or tag in {"munder", "mover", "munderover"}:
        operator = node[0].text
        if kind(node[0]) == "mo" and operator in NARY:
            lower = project(node[1]) if tag not in {"msup", "mover"} else []
            upper = project(node[-1]) if tag not in {"msub", "munder"} else []
            location = "subSup" if tag in SCRIPTS else "undOvr"
            return [element("nary", element("naryPr", element("chr", value=operator),
                            element("limLoc", value=location), element("subHide", value="off" if lower else "on"),
                            element("supHide", value="off" if upper else "on")),
                            element("sub", *lower), element("sup", *upper), element("e"))]
        if tag in SCRIPTS:
            name, args = SCRIPTS[tag]
            return [element(name, *(element(arg, *project(child)) for arg, child in zip(args, node)))]
        if tag == "mover" and node[1].text in {"\u2192", "^", "~", "\u23de", "\u00af", "\u203e", "\u2015", "\u02d9", "\u00a8"}:
            mark = node[1].text
            if mark in {"\u00af", "\u203e", "\u2015"}:
                return [element("bar", element("barPr", element("pos", value="top")), element("e", *project(node[0])))]
            accents = {"\u2192": "\u20d7", "^": "\u0302", "~": "\u0303", "\u02d9": "\u0307", "\u00a8": "\u0308"}
            return [element("acc", element("accPr", element("chr", value=accents.get(mark, mark))),
                            element("e", *project(node[0])))]
        if tag == "munder" and node[1].text in {"_", "\u0332", "\u00af", "\u2015"}:
            return [element("bar", element("barPr", element("pos", value="bot")), element("e", *project(node[0])))]
        expression = project(node[0])
        if tag in {"munder", "munderover"}:
            expression = [element("limLow", element("e", *expression), element("lim", *project(node[1])))]
        if tag in {"mover", "munderover"}:
            expression = [element("limUpp", element("e", *expression), element("lim", *project(node[-1])))]
        return expression
    if tag == "mtable":
        if node.get("dianoia-align") == "true":
            rows = []
            for row in node:
                cells = list(row)
                parts = [part for cell in cells for part in project(cell)]
                if parts and kind(parts[0]) == "r" and (parts[0].find(qn("m:t")).text or "").startswith("="):
                    relation = parts.pop(0).find(qn("m:t")).text
                    parts.insert(0, word_run("\u00a0" + relation, upright=True))
                rows.append(element("e", *(parts or [word_run("\u2009")])))
            if not rows or len(rows) > 12:
                raise ValueError("Alignment exceeds supported size")
            return [element("eqArr", *rows)]
        rows = [element("mr", *(element("e", *(project(cell) or [word_run("\u00a0")])) for cell in row)) for row in node]
        if not rows or len(rows) > 12 or max(map(len, rows)) > 12:
            raise ValueError("Matrix dimensions exceed supported size")
        columns = max(map(len, rows))
        for row in rows:
            row.extend(element("e", word_run("\u00a0")) for _ in range(columns - len(row)))
        properties = element("mPr", element("mcs", element("mc", element("mcPr",
                                element("count", value=str(columns)), element("mcJc", value="center")))))
        return [element("m", properties, *rows)]
    if tag == "menclose" and node.get("notation") == "box":
        return [element("borderBox", element("e", *sequence(node)))]
    raise ValueError(f"Unsupported MathML {tag}")


@lru_cache(maxsize=512)
def equation_xml(latex):
    if not valid_latex(latex):
        raise ValueError("Unsupported LaTeX")
    # latex2mathml maps array, matrix and cases to MathML tables. Aligned uses the same row structure.
    normalized = re.sub(r"\\begin\{(aligned|gathered)\}", r"\\begin{array}{rl}", latex)
    normalized = re.sub(r"\\end\{(aligned|gathered)\}", r"\\end{array}", normalized)
    try:
        parsed = ElementTree.fromstring(convert(normalized))
        if normalized != latex:
            for table in parsed.iter("{http://www.w3.org/1998/Math/MathML}mtable"):
                if any(cell.get("columnalign") == "right" for row in table for cell in row):
                    table.set("dianoia-align", "true")
        parts = project(parsed)
    except (*PARSER_ERRORS, SyntaxError, IndexError, KeyError, RecursionError) as error:
        raise ValueError("Unable to convert formula") from error
    if not parts:
        raise ValueError("Missing formula")
    node = etree.Element(qn("m:oMath"), nsmap={"m": MATH_NS, "dm": "urn:dianoia:math", "mc": MC_NS})
    node.append(element("box", element("e", *parts)))
    node.set(SOURCE, latex)
    node.set(f"{{{MC_NS}}}Ignorable", "dm")
    return etree.tostring(node, encoding="unicode")


def equation_source(node):
    if value := node.get(SOURCE):
        return value
    if value := node.get(PROJECTION):
        return value
    for child in node.iter(qn("w:rStyle")):
        marker = child.get(qn("w:val"), "")
        if marker.startswith(SOURCE_PREFIX):
            try:
                return urlsafe_b64decode(marker.removeprefix(SOURCE_PREFIX)).decode("utf-8")
            except (ValueError, UnicodeError):
                return ""
    return imported_equation_source(node)


def imported_equation_source(node):
    try:
        value = convert_omml(ElementTree.fromstring(etree.tostring(node))).strip("$").strip()
        return value if valid_latex(value) else ""
    except (ValueError, TypeError, IndexError, KeyError, RecursionError):
        return ""


def authored_equation(node):
    return bool(node.get(SOURCE) or any(child.get(qn("w:val"), "").startswith(SOURCE_PREFIX)
                                        for child in node.iter(qn("w:rStyle"))))


def insertion_xml(latex):
    equation = etree.fromstring(equation_xml(latex).encode())
    del equation.attrib[SOURCE]
    del equation.attrib[f"{{{MC_NS}}}Ignorable"]
    payload = SOURCE_PREFIX + urlsafe_b64encode(latex.encode()).decode("ascii")
    properties = OxmlElement("w:rPr")
    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), payload)
    properties.append(style)
    phantom = element("phant", element("phantPr", element("show", value="off"), element("zeroWid", value="on"),
                                        element("zeroAsc", value="on"), element("zeroDesc", value="on"),
                                        element("ctrlPr", properties)), element("e"))
    # The editor accepts standard OOXML only. This phantom carries the source until save.
    equation[0][0].append(phantom)
    return etree.tostring(equation, encoding="unicode")


def persist_equations(document):
    changed = False
    for node in list(document.element.body.iter(qn("m:oMath"))):
        if not node.get(SOURCE) and authored_equation(node):
            source = equation_source(node)
            if not source:
                continue
            try:
                native = etree.fromstring(equation_xml(source).encode())
            except (ValueError, SyntaxError, IndexError, KeyError, RecursionError):
                continue
            node.getparent().replace(node, native)
            changed = True
    return changed


def paragraph_text(paragraph):
    result = []
    for child in paragraph._p:
        if child.tag == qn("w:r"):
            result.append(Run(child, paragraph).text)
        elif child.tag in {qn("m:oMath"), qn("m:oMathPara")}:
            source = equation_source(child)
            result.append(r"\(" + " ".join(source.splitlines()) + r"\)" if source else "".join(
                node.text or "" for node in child.iter(qn("m:t"))
            ))
        elif child.tag in {qn("w:hyperlink"), qn("w:sdt"), qn("w:ins")}:
            result.append("".join(node.text or "" for node in child.iter(qn("w:t"))))
    return "".join(result)


def has_supported_formula(value):
    for _, latex, _ in formulas(value):
        if not latex:
            continue
        try:
            equation_xml(latex)
        except (ValueError, SyntaxError, IndexError, KeyError, RecursionError):
            return False
    return True


def append_math_text(paragraph, value, run_style=None, color=None):
    for original, latex, _ in formulas(value):
        if latex:
            try:
                paragraph._p.append(etree.fromstring(equation_xml(latex).encode()))
                continue
            except (ValueError, SyntaxError, IndexError, KeyError, RecursionError):
                pass
        run = paragraph.add_run(original)
        if run_style is not None:
            run._r.insert(0, run_style())
        if color:
            run.font.color.rgb = color


def tag_imported_equations(document):
    changed = False
    for node in document.element.body.iter(qn("m:oMath")):
        if authored_equation(node):
            continue
        source = imported_equation_source(node)
        if source and not node.get(PROJECTION):
            node.set(PROJECTION, source)
            prefix = next((name for name, namespace in node.nsmap.items() if namespace == "urn:dianoia:math"), None)
            if prefix:
                ignorable = f"{{{MC_NS}}}Ignorable"
                node.set(ignorable, " ".join(dict.fromkeys([*node.get(ignorable, "").split(), prefix])))
            changed = True
    return changed


def convert_legacy_paragraphs(paragraphs, *, prefer_math=False):
    changed = False
    for paragraph in paragraphs:
        nodes = [child for child in paragraph._p if child.tag in {qn("w:r"), qn("m:oMath")}]
        pending = []
        for node in [*nodes, None]:
            eligible = node is not None and node.tag == qn("w:r") and all(
                child.tag in {qn("w:rPr"), qn("w:t"), qn("w:br"), qn("w:tab")}
                and not (child.tag == qn("w:br") and child.get(qn("w:type"))) for child in node
            )
            if eligible and (not pending or pending[-1].getnext() is node):
                pending.append(node)
                continue
            if pending:
                changed = convert_run_group(paragraph, pending, prefer_math) or changed
            pending = [node] if eligible else []
    return changed


def convert_run_group(paragraph, runs, prefer_math):
    offsets = []
    cursor = 0
    for node in runs:
        text = Run(node, paragraph).text
        following = cursor + len(text)
        offsets.append((cursor, following, text, node.rPr))
        cursor = following
    value = "".join(item[2] for item in offsets)
    replacements = []
    cursor = 0
    for original, latex, display in formulas(value):
        stop = cursor + len(original)
        if latex and (prefer_math or display or bool(re.search(r"[\\^_+*/=<>]|[A-Za-z]", latex))):
            try:
                replacements.append((cursor, stop, etree.fromstring(equation_xml(latex).encode())))
            except (ValueError, SyntaxError, IndexError, KeyError, RecursionError):
                pass
        cursor = stop
    if not replacements:
        return False
    insert_index = paragraph._p.index(runs[0])
    cursor = 0
    for start, end, xml in [*replacements, (len(value), len(value), None)]:
        for left, right, text, style in offsets:
            lo, hi = max(left, cursor), min(right, start)
            if lo < hi:
                run = paragraph.add_run(text[lo-left:hi-left])._r
                if style is not None:
                    run.insert(0, deepcopy(style))
                paragraph._p.insert(insert_index, run)
                insert_index += 1
        if xml is not None:
            paragraph._p.insert(insert_index, xml)
            insert_index += 1
        cursor = end
    for node in runs:
        paragraph._p.remove(node)
    return True
