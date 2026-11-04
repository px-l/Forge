import { useState } from "react";

type Version = { id: string; content: { files?: Record<string, string>; html: string; summary?: string } };

export default function SourceFiles({ files, versions, disabled, restore }: {
  files: Record<string, string>;
  versions: Version[];
  disabled: boolean;
  restore: (id: string, file: string) => Promise<void>;
}) {
  const [baseId, setBaseId] = useState("");
  const [file, setFile] = useState("index.html");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = versions.find(version => version.id === baseId);
  const oldFiles = base ? base.content.files || { "index.html": base.content.html } : {};
  const names = [...new Set([...Object.keys(files), ...Object.keys(oldFiles)])];
  const before = oldFiles[file];
  const after = files[file];
  const changed = before !== after;
  return <div className="source-files">
    <label>文件 <select value={file} onChange={e => setFile(e.target.value)}>
      {names.map(name => <option key={name}>{name}</option>)}
    </select></label>
    <label>对比版本 <select value={baseId} onChange={e => {setBaseId(e.target.value); setFile("index.html");}}>
      <option value="">查看源码</option>
      {[...versions].reverse().map(version => <option key={version.id} value={version.id}>{version.id.slice(0,8)} · {version.content.summary?.slice(0,28)}</option>)}
    </select></label>
    {base && changed && <button disabled={disabled || busy} onClick={async () => {
      if (!window.confirm("将此文件恢复到所选版本？系统会保存为一个新的代码版本。")) return;
      setError("");
      setBusy(true);
      try { await restore(base.id, file); }
      catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>恢复此文件</button>}
    {error && <p role="alert">{error}</p>}
    {base && changed && <div className="source-before"><strong>历史版本</strong><pre className="source">{before ?? "此版本没有该文件"}</pre></div>}
    {base && !changed && <p>文件无差异</p>}
    <div><strong>{base ? "当前版本" : file}</strong><pre className="source">{after ?? "当前版本没有该文件"}</pre></div>
  </div>;
}
