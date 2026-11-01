import { useState, useEffect, useRef, useMemo } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  Plus,
  Command,
  Layers,
  MessageSquare,
  Code2,
  Monitor,
  Smartphone,
  Check,
  LoaderCircle,
  Settings2,
  ChevronDown,
  Download,
  History,
  Play,
  Square,
  Image,
  ShieldCheck,
  TriangleAlert,
  PanelLeftClose,
  Folder,
  CheckCircle2,
  X,
  RotateCcw,
  Workflow,
  ExternalLink,
  Copy,
  FileText,
} from "lucide-react";
import ProjectMemory from "./ProjectMemory";
import { previewDocument } from "./preview";
type Artifact = {
  id: string;
  task_id: string;
  kind: string;
  content: any;
  created: string;
};
type Task = { id: string; status: string; payload: string; created: string };
type Project = {
  id: string;
  current_code_id?: string;
  memory?: any;
  name: string;
  created: string;
  tasks?: Task[];
  artifacts?: Artifact[];
};
type Event = {
  type: string;
  node?: string;
  status?: string;
  summary?: string;
  message?: string;
  request?: any;
  time: string;
};
async function api(path: string, body?: unknown) {
  const r = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.error || "请求失败");
  return data;
}
const steps = [
  ["clarify", "需求澄清"],
  ["design", "原型设计"],
  ["develop", "代码开发"],
  ["validate", "UI 验证"],
  ["deliver", "交付预览"],
];
const statuses: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  needs_input: "等待确认",
  completed: "已完成",
  failed: "执行失败",
  interrupted: "已中断",
  cancelled: "已取消",
  needs_review: "待人工检查",
};
export default function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project | null>(null),
    [taskId, setTaskId] = useState(""),
    [events, setEvents] = useState<Event[]>([]),
    [prompt, setPrompt] = useState(""),
    [tab, setTab] = useState("preview"),
    [version, setVersion] = useState(""),
    [phone, setPhone] = useState(false),
    [demo, setDemo] = useState(false),
    [design, setDesign] = useState(true),
    [mode, setMode] = useState("new"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [settings, setSettings] = useState(false),
    [config, setConfig] = useState<any>(null),
    [answer, setAnswer] = useState(""),
    [history, setHistory] = useState(false),
    [copied, setCopied] = useState(false),
    [reload, setReload] = useState(0);
  const iframe = useRef<HTMLIFrameElement>(null),
    token = useRef(""),
    selected = useRef(""),
    lastEvent = useRef(0),
    end = useRef<HTMLDivElement>(null);
  const artifacts = project?.artifacts || [],
    codes = artifacts.filter((a) => a.kind === "code"),
    task = project?.tasks?.find((t) => t.id === taskId) || project?.tasks?.at(-1),
    candidate = codes.filter(a=>a.task_id===task?.id).at(-1),
    code = codes.find(a=>a.id===(version || (['running','needs_input'].includes(task?.status||'') ? candidate?.id : project?.current_code_id))) || candidate || codes.at(-1),
    active = busy || ["running", "queued"].includes(task?.status || ""),
    pending = [...events]
      .reverse()
      .find((e) => e.type === "needs_input")?.request;
  const relevant = artifacts.filter((a) => a.task_id === task?.id),
    target = [...relevant].reverse().find((a) => a.kind === "design") || artifacts.find(a=>a.id===code?.content.design_id),
    requirements = [...relevant]
      .reverse()
      .find((a) => a.kind === "requirements"),
    report = [...artifacts]
      .reverse()
      .find((a) => a.kind === "validation" && a.content.code_id === code?.id),
    screenshot = [...artifacts]
      .reverse()
      .find((a) => a.kind === "screenshot" && a.content.code_id === code?.id);
  async function copyPreview() {
    if (!code) return;
    try {
      const result = await api('/artifacts/'+code.id+'/share', {});
      await navigator.clipboard.writeText(result.url);
      setCopied(true);
      setTimeout(()=>setCopied(false),2500);
    } catch (e) { setError('复制预览链接失败，请重试。'); }
  }
  async function loadProjects() {
    setProjects(await api("/projects"));
  }
  async function refresh(pid: string) {
    const p = await api("/projects/" + pid);
    if (selected.current === pid) setProject(p);
  }
  useEffect(() => {
    api("/health")
      .then(setConfig)
      .catch(() => setError("后端未连接，请启动 FastAPI 服务。"));
    loadProjects().catch(() => {});
    const id = localStorage.getItem("forge-active-project");
    if (id) openProject(id);
  }, []);
  async function openProject(id: string) {
    if (active) return;
    selected.current = id;
    setEvents([]);
    setError("");
    setVersion("");
    setProject(null);
    localStorage.setItem("forge-active-project", id);
    try {
      const p = await api("/projects/" + id);
      if (selected.current !== id) return;
      setProject(p);
      setDemo(
        p.tasks?.length ? !!JSON.parse(p.tasks.at(-1).payload).demo : false,
      );
      setTaskId(p.tasks?.at(-1)?.id || "");
      setTab("preview");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    if (!taskId || !project) return;
    let closed = false;
    lastEvent.current = 0;
    setEvents([]);
    const es = new EventSource("/api/tasks/" + taskId + "/events");
    es.onmessage = (e) => {
      if (closed) return;
      lastEvent.current = Number(e.lastEventId);
      const item = JSON.parse(e.data);
      setEvents((old) => [...old, item]);
      if (item.type === "artifact" || item.type === "status")
        refresh(project.id);
    };
    es.addEventListener("settled", () => {
      es.close();
      refresh(project.id);
    });
    es.onerror = () => {
      if (!closed) refresh(project.id).catch(() => {});
    };
    return () => {
      closed = true;
      es.close();
    };
  }, [taskId, reload]);
  useEffect(() => {
    const container = end.current?.parentElement;
    if (container)
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [events.length]);
  useEffect(() => {
    if (task?.status === "needs_input" && pending?.node === "design")
      setTab("design");
    else if (task?.status === "completed" || (task?.status === "needs_input" && pending?.node === "review")) setTab("preview");
  }, [task?.status, pending?.node]);
  const document = useMemo(() => {
    if (!code || !project) return "";
    token.current = crypto.randomUUID();
    let data = {};
    try {
      data = JSON.parse(
        localStorage.getItem("forge-app-data:" + project.id) || "{}",
      );
    } catch {}
    let sessionData = {};
    try { sessionData = JSON.parse(sessionStorage.getItem("forge-app-session:"+project.id)||"{}"); } catch {}
    return previewDocument(code.content.html, token.current, data, sessionData);
  }, [code?.id, project?.id]);
  useEffect(() => {
    function receive(e: MessageEvent) {
      if (
        e.source !== iframe.current?.contentWindow ||
        e.data?.forge !== token.current ||
        !project
      )
        return;
      if (e.data.type === "storage") {
        try {
          const raw = JSON.stringify(e.data.data);
          if (raw.length > 2000000) throw Error("应用数据超过2MB限制");
          if(e.data.area === 'session') sessionStorage.setItem("forge-app-session:"+project.id,raw);
          else localStorage.setItem("forge-app-data:" + project.id, raw);
        } catch {
          setError("应用数据保存失败：请检查浏览器存储空间。");
        }
      }
      if (e.data.type === "error")
        setError("预览运行错误：" + String(e.data.error));
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [project?.id]);
  async function submit(text = prompt) {
    if (!text.trim() || active) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        prompt: text,
        demo,
        wants_design: design,
        mode: project && code ? "modify" : mode,
        base_code_id: code?.id,
      };
      const r = project
        ? await api("/projects/" + project.id + "/tasks", body)
        : await api("/projects", body);
      const pid = project?.id || r.project_id;
      selected.current = pid;
      localStorage.setItem("forge-active-project", pid);
      setPrompt("");
      setVersion("");
      setEvents([]);
      setTab("preview");
      await refresh(pid);
      setTaskId(r.task_id);
      setReload((x) => x + 1);
      await loadProjects();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resume(value?: any) {
    if (!task) return;
    setBusy(true);
    setError("");
    try {
      await api("/tasks/" + task.id + "/resume", { answer: value ?? null });
      await refresh(project!.id);
      setReload((x) => x + 1);
      setAnswer("");
      setTab("preview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!task) return;
    try {
      await api("/tasks/" + task.id + "/cancel", {});
      await refresh(project!.id);
      setReload((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function reset() {
    if (active) return;
    selected.current = "";
    setProject(null);
    setTaskId("");
    setVersion("");
    setEvents([]);
    setPrompt("");
    setError("");
    localStorage.removeItem("forge-active-project");
  }
  return (
    <div className="app">
      <aside className="sidebar">
        <button className="brand" onClick={reset}>
          <span className="brand-mark">
            <Command size={22} />
          </span>
          forge<span className="beta">BETA</span>
        </button>
        <button className="new-project" onClick={reset} disabled={active}>
          <Plus size={17} /> 新建项目 <kbd>＋</kbd>
        </button>
        <div className="nav-item selected">
          <Layers size={17} /> 我的工作空间 <span>{projects.length}</span>
        </div>
        <div className="sidebar-heading">
          最近项目 <Folder size={13} />
        </div>
        <div className="project-list">
          {projects.map((p) => (
            <button
              disabled={active}
              className={
                "project-link " + (p.id === project?.id ? "current" : "")
              }
              key={p.id}
              onClick={() => openProject(p.id)}
            >
              <MessageSquare size={15} />
              <span>{p.name}</span>
            </button>
          ))}
          {!projects.length && (
            <p className="no-project">
              你的下一个想法，
              <br />
              从这里开始。
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="workspace-note">
            <span className="green-dot" /> 一个想法，一次完整交付
            <p>需求 · 设计 · 开发 · 验证</p>
          </div>
          <button className="settings" onClick={() => setSettings(true)}>
            <Settings2 size={17} /> 模型与运行设置
          </button>
          <div className="profile">
            <span>P</span>
            <div>
              个人工作空间<small>匿名访客 · 当前浏览器</small>
            </div>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <PanelLeftClose size={17} />
            <span>工作空间</span>
            <span className="slash">/</span>
            <strong>{project?.name || "新建项目"}</strong>
          </div>
          <button className="quiet" onClick={() => setSettings(true)}>
            <span
              className={"green-dot " + (!config?.configured ? "yellow" : "")}
            />
            {config?.configured ? "模型已连接" : "待配置模型"}
            <Settings2 size={14} />
          </button>
        </header>
        {!project ? (
          <div className="home">
            <div className="eyebrow">
              <span /> YOUR AI DELIVERY TEAM
            </div>
            <h1>
              把想法，
              <br />
              <span>交付成真正的应用。</span>
            </h1>
            <p className="intro">
              从一句需求到可运行的产品。让 AI 负责执行，让每一步清晰可见。
            </p>
            <div className="composer hero-composer">
              <textarea
                aria-label="应用需求"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="描述你想开发的应用，比如：一个小恐龙跑酷小游戏"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
                }}
              />
              <div className="composer-actions">
                <div className="model-chip">
                  <span className="model-symbol">✳</span> 千问 Agent{" "}
                  <ChevronDown size={12} />
                </div>
                <button
                  className="send"
                  aria-label="开始创建"
                  disabled={busy || !prompt.trim()}
                  onClick={() => submit()}
                >
                  {busy ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <ArrowUp size={20} />
                  )}
                </button>
              </div>
            </div>
            <div className="options">
              <label>
                <input
                  type="checkbox"
                  checked={design}
                  onChange={(e) => setDesign(e.target.checked)}
                />{" "}
                开发前生成设计图
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={demo}
                  onChange={(e) => setDemo(e.target.checked)}
                />{" "}
                演示模式
              </label>
              <select
                aria-label="任务类型"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="new">完整开发流程</option>
                <option value="prototype">仅生成原型</option>
              </select>
            </div>
            {demo && (
              <div className="demo-note">
                演示模式使用固定示例，不调用模型；浏览器验证仍真实执行。
              </div>
            )}
            <div className="suggestions">
              {[
                [
                  "任务管理",
                  "一个支持新增、完成、筛选任务和进度统计的任务管理应用",
                ],
                [
                  "个人记账",
                  "一个支持收支录入、分类筛选和月度汇总的个人记账工具",
                ],
                [
                  "研发交付",
                  "一个包含任务看板、交付物清单和发布检查的研发交付工作台",
                ],
              ].map(([name, p]) => (
                <button key={name} onClick={() => setPrompt(p)}>
                  <Plus size={14} />
                  {name}
                  <ArrowUpRight size={13} />
                </button>
              ))}
            </div>
            <div className="workflow-overview">
              {steps.map(([id, label], i) => (
                <div key={id}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  {label}
                  {i < 4 && <i>→</i>}
                </div>
              ))}
            </div>
            <div className="home-foot">
              <ShieldCheck size={14} /> 无需注册 · 项目持久化 · 交付版本可追溯
            </div>
          </div>
        ) : (
          <div className="workbench">
            <section className="conversation">
              <div className="conversation-heading">
                <div>
                  <Workflow size={17} />
                  <strong>研发执行</strong>
                </div>
                <span className={"status " + task?.status}>
                  {statuses[task?.status || ""] || "准备就绪"}
                </span>
              </div>
              <div className="timeline-scroll">
                <div className="request-card">
                  <small>你的需求</small>
                  {task ? JSON.parse(task.payload).prompt : project.name}
                </div>
                {task && JSON.parse(task.payload).demo && (
                  <div className="demo-banner">
                    演示模式 · 固定示例，未调用大模型
                  </div>
                )}
                <div className="agent-intro">
                  <span className="avatar">
                    <Command size={17} />
                  </span>
                  <div>
                    <strong>Forge 编排器</strong>
                    <p>
                      按固定工作流分配专项节点，保存产物，并在关键步骤等待你的确认。
                    </p>
                  </div>
                </div>
                <div className="steps">
                  {steps.map(([id, label]) => {
                    const ev = [...events]
                      .reverse()
                      .find((e) => e.type === "node" && e.node === id);
                    return (
                      <div
                        className={"step " + (ev?.status || "pending")}
                        key={id}
                      >
                        <span className="step-icon">
                          {ev?.status === "completed" ? (
                            <Check size={13} />
                          ) : ev?.status === "running" ? (
                            <LoaderCircle className="spin" size={13} />
                          ) : ev?.status === "failed" ? (
                            <X size={13} />
                          ) : (
                            <span />
                          )}
                        </span>
                        <div>
                          <strong>{label}</strong>
                          <small>
                            {ev?.status === "running"
                              ? (ev.summary === "正在重新生成" ? "正在重新生成…" : "正在执行…")
                              : ev?.status === "completed"
                                ? "产物已保存"
                                : ev?.status === "failed"
                                  ? "失败现场已保存"
                                  : "等待执行 / 按条件跳过"}
                          </small>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {requirements && (
                  <div className="artifact-card">
                    <small>需求产物</small>
                    <strong>{requirements.content.title || "本次修改"}</strong>
                    <p>{requirements.content.summary}</p>
                    {requirements.content.features?.map((f: string) => (
                      <div className="feature" key={f}>
                        <Check size={12} />
                        {f}
                      </div>
                    ))}
                  </div>
                )}
                {task?.status === "needs_input" && pending && (
                  <div className="approval">
                    <strong>{pending.title}</strong>
                    {pending.questions?.map((q: string) => (
                      <p key={q}>{q}</p>
                    ))}
                    {pending.node === "review" ? (
                      <><p>{pending.automatic_limit_reached ? '本轮自动生成已完成，你可以保留当前网站，或继续重新生成。' : '网站与设计仍有少量差异，你可以预览后决定是否重新生成。'}</p><button className="primary" disabled={busy} onClick={()=>resume({regenerate:false})}>保留当前网站</button><button className="quiet" disabled={busy} onClick={()=>resume({regenerate:true})}>重新生成</button></>
                    ) : pending.node === "design" ? (
                      <>
                        <p>在右侧查看设计图，确认后开始代码开发。</p>
                        <button
                          className="primary"
                          onClick={() => resume({ approved: true })}
                          disabled={busy}
                        >
                          确认设计，继续开发 <ArrowUpRight size={14} />
                        </button>
                        <button className="quiet" onClick={cancel}>
                          取消本次任务
                        </button>
                      </>
                    ) : (
                      <>
                        <textarea
                          aria-label="补充需求"
                          value={answer}
                          onChange={(e) => setAnswer(e.target.value)}
                          placeholder="补充你的要求…"
                        />
                        <button
                          className="primary"
                          disabled={!answer.trim() || busy}
                          onClick={() => resume(answer)}
                        >
                          提交并继续
                        </button>
                      </>
                    )}
                  </div>
                )}
                {events
                  .slice(events.map(e=>e.type).lastIndexOf('attempt_started')+1)
                  .filter((e) => ["error", "retry"].includes(e.type) && !['completed','needs_review'].includes(task?.status||''))
                  .map((e, i) => (
                    <div className="event-error" key={i}>
                      <TriangleAlert size={14} />
                      {e.message || e.summary}
                    </div>
                  ))}
                {["failed", "interrupted"].includes(task?.status || "") && (
                  <button
                    className="retry-button"
                    disabled={busy}
                    onClick={() => resume()}
                  >
                    <RotateCcw size={14} /> 从检查点重试
                  </button>
                )}
                {["completed", "needs_review"].includes(task?.status || "") && (
                  <div className="delivery-note">
                    <CheckCircle2 size={18} />
                    <div>
                      <strong>{code ? '网站已生成' : '原型已生成'}</strong>
                      <p>{code ? '可在当前窗口预览查看，或复制链接至其他浏览器查看。' : '可在设计标签中查看原型。'}</p>
                      {code && <button className="quiet" onClick={copyPreview}><Copy size={14}/>{copied?'已复制':'复制预览网址'}</button>}
                    </div>
                  </div>
                )}
                <div ref={end} />
              </div>
              <div className="followup">
                <div className="composer">
                  <textarea
                    aria-label="修改要求"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={
                      active
                        ? "Agent 正在执行任务…"
                        : "继续描述修改，或输入修复要求…"
                    }
                    disabled={active}
                  />
                  <div className="composer-actions">
                    <small>
                      {code ? "基于当前选中版本修改" : "开始新的开发任务"}
                    </small>
                    {active ? (
                      <button
                        className="send stop"
                        aria-label="停止任务"
                        onClick={cancel}
                      >
                        <Square size={15} />
                      </button>
                    ) : (
                      <button
                        className="send"
                        aria-label="提交修改"
                        disabled={
                          !prompt.trim() || task?.status === "needs_input"
                        }
                        onClick={() => submit()}
                      >
                        <ArrowUp size={18} />
                      </button>
                    )}
                  </div>
                </div>
                <label className="tiny">
                  <input
                    type="checkbox"
                    checked={demo}
                    onChange={(e) => setDemo(e.target.checked)}
                  />{" "}
                  本次使用演示模式
                </label>
              </div>
            </section>
            <section className="canvas">
              <div className="canvas-toolbar">
                <div className="tabs">
                  {[
                    ["requirements", "需求", FileText],
                    ["design", "设计", Image],
                    ["code", "代码", Code2],
                    ["preview", "预览", Monitor],
                  ].map(([id, label, Icon]) => (
                    <button
                      className={tab === id ? "active" : ""}
                      key={String(id)}
                      onClick={() => setTab(String(id))}
                    >
                      {typeof Icon !== "string" && <Icon size={15} />}
                      <span>{String(label)}</span>
                    </button>
                  ))}
                </div>
                <div className="tools">
                  {code && <button title="复制预览网址" aria-label="复制预览网址" onClick={copyPreview}><Copy size={16}/>{copied && <span>已复制</span>}</button>}
                  <button title="历史版本" onClick={() => setHistory(!history)}>
                    <History size={16} />
                  </button>
                  {code && (
                    <a
                      title="下载源码"
                      href={"/api/artifacts/" + code.id + "/download"}
                    >
                      <Download size={16} />
                    </a>
                  )}
                </div>
              </div>
              {history && (
                <div className="versions">
                  <strong>恢复交付版本</strong>
                  <small>切换或恢复仅影响代码，不回滚业务数据。</small>
                  {codes.map((a, i) => (
                    <button
                      key={a.id}
                      onClick={() => {
                        api("/projects/" + project.id + "/restore", {
                          code_id: a.id,
                        })
                          .then(() => {
                            setVersion(a.id);
                            setHistory(false);
                            setTab("preview");
                            refresh(project.id);
                          })
                          .catch((e) => setError(e.message));
                      }}
                    >
                      <span>
                        V{i + 1} · {a.content.summary.slice(0, 34)}
                      </span>
                      {a.id === code?.id && <Check size={14} />}
                    </button>
                  ))}
                </div>
              )}
              <div className="browser-bar">
                <span className="traffic">
                  <i />
                  <i />
                  <i />
                </span>
                <div>
                  <ShieldCheck size={12} />
                  {tab === "preview"
                    ? "应用预览 · 隔离运行"
                    : tab === "design"
                      ? "目标设计 · 开发参考"
                      : tab === "code"
                        ? "源代码 · 完整快照"
                        : "需求说明 · 已梳理"}
                </div>
                <button title="切换预览尺寸" onClick={() => setPhone(!phone)}>
                  {phone ? <Smartphone size={15} /> : <Monitor size={15} />}
                </button>
              </div>
              <div className={"canvas-body " + (phone ? "mobile" : "")}>
                {tab === "preview" ? (
                  code ? (
                    <iframe
                      title="生成应用预览"
                      ref={iframe}
                      sandbox="allow-scripts allow-forms"
                      srcDoc={document}
                    />
                  ) : (
                    <div className="empty">
                      <div className="empty-orbit">
                        <Layers size={30} />
                      </div>
                      <h3>应用即将在这里呈现</h3>
                      <p>
                        从需求出发，经过设计、开发与验证。
                        <br />
                        每一步都有记录，每次交付都有依据。
                      </p>
                      {active && (
                        <span className="working">
                          <LoaderCircle className="spin" size={13} /> Agent
                          正在工作
                        </span>
                      )}
                    </div>
                  )
                ) : tab === "design" ? (
                  target ? (
                    <div className="design-view">
                      <div className="image-caption">
                        目标效果图{" "}
                        {task && JSON.parse(task.payload).demo
                          ? "· 演示参考图"
                          : "· AI 生成"}
                      </div>
                      <img alt="目标效果图" src={target.content.image} />
                    </div>
                  ) : (
                    <div className="empty">
                      <Image size={32} />
                      <h3>尚无目标效果图</h3>
                      <p>勾选开发前生成设计图，或创建原型任务。</p>
                    </div>
                  )
                ) : tab === "code" ? (
                  code ? (
                    <pre className="source">{code.content.html}</pre>
                  ) : (
                    <div className="empty">
                      <Code2 size={32} />
                      <h3>等待代码生成</h3>
                    </div>
                  )
                ) : (
                  <div className="requirements-view">
                    {project.memory && <ProjectMemory key={project.id} memory={project.memory} locked={active||['needs_input','interrupted'].includes(task?.status||'')} onSave={async value=>{const cleaned={...value};for(const field of ['features','design_constraints','protected_items'])cleaned[field]=value[field].map((x:string)=>x.trim()).filter(Boolean);await api('/projects/'+project.id+'/memory',cleaned);await refresh(project.id);}}/>}
                    {requirements ? <><div className="eyebrow">PRODUCT REQUIREMENTS</div><h2>{requirements.content.title || '梳理后的需求'}</h2><p>{requirements.content.summary}</p>{requirements.content.features?.length>0&&<><h3>核心功能</h3><ul>{requirements.content.features.map((f:string,i:number)=><li key={i}>{f}</li>)}</ul></>}{requirements.content.acceptance?.length>0&&<><h3>验收标准</h3><ul>{requirements.content.acceptance.map((f:string,i:number)=><li key={i}>{f}</li>)}</ul></>}{requirements.content.clarification&&<><h3>补充说明</h3><p>{requirements.content.clarification}</p></>}</> : <div className="empty"><FileText size={32}/><h3>正在梳理需求</h3><p>需求梳理完成后会在这里展示。</p></div>}
                  </div>
                )}
              </div>
              <footer className="canvas-footer">
                <span>
                  <span className="green-dot" />
                  {code
                    ? `V${codes.findIndex((a) => a.id === code.id) + 1} · 代码已保存`
                    : "等待首个交付版本"}
                </span>
                <span>
                  {phone ? "390 px" : "自适应预览"} · 浏览器数据独立保存
                </span>
              </footer>
            </section>
          </div>
        )}
        {error && (
          <div className="toast" role="alert">
            <TriangleAlert size={17} />
            <span>{error}</span>
            <button aria-label="关闭提示" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
      </main>
      {settings && (
        <div className="modal-backdrop" onClick={() => setSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              aria-label="关闭设置"
              onClick={() => setSettings(false)}
            >
              <X size={19} />
            </button>
            <span className="eyebrow">WORKSPACE SETTINGS</span>
            <h2>模型与运行配置</h2>
            <p>密钥仅保存在服务端，浏览器不会读取。</p>
            <div className="setting-row">
              <span>代码 / 视觉模型</span>
              <strong>{config?.model || "qwen3.7-plus"}</strong>
            </div>
            <div className="setting-row">
              <span>连接状态</span>
              <strong>{config?.configured ? "已配置密钥" : "尚未配置"}</strong>
            </div>
            <pre>
              DASHSCOPE_API_KEY=你的百炼密钥{"\n"}CODE_MODEL=qwen3.7-plus{"\n"}
              VISION_MODEL=qwen3.7-plus{"\n"}IMAGE_MODEL=qwen-image-3.0
            </pre>
            <p>
              在项目根目录 .env 中配置并重启后端。浏览器 Worker
              需单独启动。没有密钥时，可通过演示模式验证固定流程。
            </p>
            <div className="setting-foot">
              <ShieldCheck size={16} /> 项目与检查点保存于服务端
              SQLite；生成应用的数据保存于当前浏览器。
            </div>
            <button className="primary" onClick={() => setSettings(false)}>
              知道了
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
