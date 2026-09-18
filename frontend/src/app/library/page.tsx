"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { apiRequest, clearToken, getToken, Paper, User } from "@/lib/api";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function LibraryPage() {
  const router = useRouter();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  async function loadLibrary(token: string) {
    const [currentUser, paperList] = await Promise.all([
      apiRequest<User>("/auth/me", {}, token),
      apiRequest<Paper[]>("/papers", {}, token),
    ]);
    setUser(currentUser);
    setPapers(paperList);
  }

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    Promise.all([
      apiRequest<User>("/auth/me", {}, token),
      apiRequest<Paper[]>("/papers", {}, token),
    ])
      .then(([currentUser, paperList]) => {
        setUser(currentUser);
        setPapers(paperList);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = getToken();
    if (!token || !selectedFile) return;

    setUploading(true);
    setMessage("");
    const form = new FormData();
    form.append("file", selectedFile);
    try {
      await apiRequest<Paper>("/papers", { method: "POST", body: form }, token);
      await loadLibrary(token);
      setSelectedFile(null);
      const input = event.currentTarget.elements.namedItem("pdf") as HTMLInputElement;
      input.value = "";
      setMessage("上传成功");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(paper: Paper) {
    if (!window.confirm(`确定删除“${paper.title || paper.original_filename}”吗？`)) return;
    const token = getToken();
    if (!token) return;
    try {
      await apiRequest<void>(`/papers/${paper.id}`, { method: "DELETE" }, token);
      setPapers((current) => current.filter((item) => item.id !== paper.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败");
    }
  }

  function logout() {
    clearToken();
    router.push("/login");
  }

  if (loading) return <main className="center-state">正在加载论文库…</main>;

  return (
    <main className="app-shell">
      <header className="app-header">
        <Link href="/library" className="brand">PaperGPT</Link>
        <div className="header-actions">
          <span>{user?.name}</span>
          <button className="text-button" onClick={logout}>退出登录</button>
        </div>
      </header>

      <section className="library-heading">
        <div>
          <p className="eyebrow">Paper Library</p>
          <h1>我的论文</h1>
          <p className="muted">上传并管理 PDF。内容解析与 AI 功能将在后续阶段提供。</p>
        </div>
        <form className="upload-box" onSubmit={handleUpload}>
          <input name="pdf" type="file" accept="application/pdf,.pdf" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} required />
          <button className="primary-button" disabled={uploading || !selectedFile}>
            {uploading ? "上传中…" : "上传 PDF"}
          </button>
        </form>
      </section>

      {message && <p className="status-message" role="status">{message}</p>}

      {papers.length === 0 ? (
        <section className="empty-state">
          <h2>还没有论文</h2>
          <p>上传一篇 PDF 开始阅读。</p>
        </section>
      ) : (
        <section className="paper-grid">
          {papers.map((paper) => (
            <article className="paper-card" key={paper.id}>
              <div>
                <span className="status-badge">{paper.parse_status}</span>
                <h2>{paper.title || paper.original_filename}</h2>
                <p>{paper.original_filename}</p>
                <time>{formatDate(paper.created_at)}</time>
              </div>
              <div className="card-actions">
                <Link className="secondary-button" href={`/paper/${paper.id}`}>打开</Link>
                <button className="danger-button" onClick={() => handleDelete(paper)}>删除</button>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
