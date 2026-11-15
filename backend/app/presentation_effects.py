from functools import lru_cache
from io import BytesIO
from itertools import count

from PIL import Image, ImageDraw
from pptx.media import Video
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.oxml.shapes.picture import CT_Picture
from pptx.oxml.xmlchemy import OxmlElement

from .presentation_media import MIME, media_path


@lru_cache(maxsize=2)
def poster(kind):
    image = Image.new("RGB", (320, 180), "#1b2441")
    draw = ImageDraw.Draw(image)
    draw.ellipse((124, 54, 196, 126), fill="#e2e7fa")
    if kind == "video":
        draw.polygon([(151, 71), (151, 109), (178, 90)], fill="#29375c")
    else:
        draw.polygon([(141, 83), (152, 83), (163, 73), (163, 107), (152, 97), (141, 97)], fill="#29375c")
        draw.arc((157, 72, 182, 108), -65, 65, fill="#29375c", width=4)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def add_native_media(slide, item, asset, position):
    path = media_path(asset)
    media = Video.from_path_or_file_like(str(path), MIME[item.kind])
    part = slide.part
    binary = part.package.get_or_add_media_part(media)
    media_id = part.relate_to(binary, RT.MEDIA)
    file_id = part.relate_to(binary, RT.AUDIO if item.kind == "audio" else RT.VIDEO)
    _, poster_id = part.get_or_add_image_part(BytesIO(poster(item.kind)))
    shapes = slide.shapes
    picture = CT_Picture.new_video_pic(shapes._next_shape_id, "Media", file_id, media_id, poster_id, *position)
    if item.kind == "audio":
        picture.find(".//" + qn("a:videoFile")).tag = qn("a:audioFile")
    shapes._spTree.append(picture)
    shape = shapes._shape_factory(picture)
    shape.name = asset.filename
    return shape


def child(parent, tag, **attributes):
    node = OxmlElement(f"p:{tag}")
    for key, value in attributes.items():
        node.set(key, str(value))
    parent.append(node)
    return node


def target(parent, shape_id=None):
    container = child(parent, "tgtEl")
    return child(container, "sldTgt") if shape_id is None else child(container, "spTgt", spid=shape_id)


def condition(parent, kind="stCondLst", delay=0, event=None, shape_id=None):
    node = child(child(parent, kind), "cond", delay=delay)
    if event:
        node.set("evt", event)
        target(node, shape_id)
    return node


class SlideTiming:
    EFFECTS = {
        "fade_in": (10, "entr", 0), "fly_in": (2, "entr", 4),
        "emphasis": (6, "emph", 0), "fade_out": (10, "exit", 0),
    }

    def __init__(self):
        self.ids = count(1)
        self.media = []

    def add_media(self, shape_id, kind, duration):
        self.media.append((shape_id, kind, duration))

    def time(self, parent, **attrs):
        return child(parent, "cTn", id=next(self.ids), **attrs)

    def block(self, parent, delay):
        time = self.time(child(parent, "par"), fill="hold")
        condition(time, delay=delay)
        return child(time, "childTnLst")

    def behavior(self, parent, shape_id, duration, attribute=None, delay=None, hold=False, **attrs):
        behavior = child(parent, "cBhvr")
        if attribute in {"ppt_x", "ppt_y"}:
            behavior.set("additive", "base")
        time = self.time(behavior, dur=duration, **attrs)
        if hold:
            time.set("fill", "hold")
        if delay is not None:
            condition(time, delay=delay)
        target(behavior, shape_id)
        if attribute:
            child(child(behavior, "attrNameLst"), "attrName").text = attribute
        return behavior

    def set_visibility(self, parent, shape_id, visible, delay):
        action = child(parent, "set")
        self.behavior(action, shape_id, 1, "style.visibility", delay, hold=True)
        child(child(action, "to"), "strVal", val="visible" if visible else "hidden")

    def animation(self, parent, animation, shape_id, group):
        effect, duration = animation.effect, animation.duration_ms
        preset, category, subtype = self.EFFECTS[effect]
        node = self.time(child(parent, "par"), presetID=preset, presetClass=category, presetSubtype=subtype,
                         fill="hold", grpId=group, nodeType="clickEffect" if animation.trigger == "click" else "afterEffect")
        condition(node)
        actions = child(node, "childTnLst")
        if category == "entr":
            self.set_visibility(actions, shape_id, True, 0)
        if effect in {"fade_in", "fade_out"}:
            action = child(actions, "animEffect", transition="in" if effect == "fade_in" else "out", filter="fade")
            self.behavior(action, shape_id, duration)
            if effect == "fade_out":
                self.set_visibility(actions, shape_id, False, duration - 1)
        elif effect == "fly_in":
            for axis, start in (("x", "#ppt_x"), ("y", "1+#ppt_h/2")):
                action = child(actions, "anim", calcmode="lin", valueType="num")
                self.behavior(action, shape_id, duration, f"ppt_{axis}", hold=True)
                values = child(action, "tavLst")
                for offset, value in ((0, start), (100000, f"#ppt_{axis}")):
                    child(child(child(values, "tav", tm=offset), "val"), "strVal", val=value)
        else:
            action = child(actions, "animScale")
            self.behavior(action, shape_id, duration // 2, hold=True, autoRev=1)
            child(action, "by", x=112000, y=112000)

    def playback(self, root, shape_id, kind, duration):
        seq = child(root, "seq", concurrent=1, nextAc="seek")
        time = self.time(seq, restart="whenNotActive", fill="hold", evtFilter="cancelBubble", nodeType="interactiveSeq")
        condition(time, event="onClick", shape_id=shape_id)
        child(child(time, "endSync", evt="end", delay=0), "rtn", val="all")
        group = self.block(self.block(child(time, "childTnLst"), 0), 0)
        audio = kind == "audio"
        effect = self.time(child(group, "par"), presetID=1 if audio else 2, presetClass="mediacall", presetSubtype=0,
                           fill="hold", nodeType="clickEffect")
        condition(effect)
        command = child(child(effect, "childTnLst"), "cmd", type="call", cmd="playFrom(0.0)" if audio else "togglePause")
        self.behavior(command, shape_id, duration if audio else 1, hold=True)
        condition(seq, "nextCondLst", event="onClick", shape_id=shape_id)
        media = child(child(root, kind), "cMediaNode", vol=80000)
        media_time = self.time(media, fill="hold", display=0)
        condition(media_time, delay="indefinite")
        if audio:
            condition(media_time, "endCondLst", event="onStopAudio")
        target(media, shape_id)

    def write(self, slide, animations, target_ids):
        if not (animations or self.media):
            return
        timing = OxmlElement("p:timing")
        slide._element.insert_element_before(timing, "p:extLst")
        root = self.time(child(child(timing, "tnLst"), "par"), dur="indefinite", restart="never", nodeType="tmRoot")
        children = child(root, "childTnLst")
        built = []
        if animations:
            seq = child(children, "seq", concurrent=1, nextAc="seek")
            groups = child(self.time(seq, dur="indefinite", nodeType="mainSeq"), "childTnLst")
            current = None
            counts = {}
            for animation in animations:
                shape_id = target_ids[animation.target_id]
                if current is None or animation.trigger == "click":
                    current = self.block(groups, "indefinite" if animation.trigger == "click" else 0)
                    delay = 0
                group = counts.get(shape_id, 0)
                self.animation(self.block(current, delay), animation, shape_id, group)
                built.append((shape_id, group))
                counts[shape_id] = group + 1
                delay += animation.duration_ms
            condition(seq, "prevCondLst", event="onPrev")
            condition(seq, "nextCondLst", event="onNext")
        for entry in self.media:
            self.playback(children, *entry)
        if built:
            build_list = child(timing, "bldLst")
            for shape_id, group in sorted(built):
                child(build_list, "bldP", spid=shape_id, grpId=group, animBg=1)
