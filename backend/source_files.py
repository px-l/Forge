"""Source snapshots for the isolated HTML runtime."""
import re

NAMES = ("index.html", "styles.css", "app.js")


def snapshot(content):
    return content.get("files") or {"index.html": content["html"]}


def bundle(files):
    if not isinstance(files, dict) or not isinstance(files.get("index.html"), str):
        raise ValueError("缺少 index.html")
    if any(name not in NAMES or not isinstance(value, str) for name, value in files.items()):
        raise ValueError("仅支持 index.html、styles.css 与 app.js")
    if sum(map(len, files.values())) > 380000:
        raise ValueError("源码超出大小限制")
    html = files["index.html"]
    for name, tag, end in (("styles.css", "style", "head"), ("app.js", "script", "body")):
        value = files.get(name)
        if not value:
            continue
        if re.search(rf"</{tag}\b", value, re.I):
            raise ValueError(f"{name} 含有不支持的 HTML 结束标签")
        wrapped = f"<{tag}>\n{value}\n</{tag}>"
        pattern = rf"</{end}\s*>"
        if re.search(pattern, html, re.I):
            html = re.sub(pattern, lambda m: wrapped + m[0], html, count=1, flags=re.I)
        else:
            html = wrapped + html if end == "head" else html + wrapped
    return html


def apply_changes(base, changes):
    if not isinstance(changes, dict) or not changes or any(name not in NAMES for name in changes):
        raise ValueError("无效的文件修改")
    files = dict(base)
    for name, content in changes.items():
        if content is None:
            files.pop(name, None)
        else:
            files[name] = content
    return files, bundle(files)
