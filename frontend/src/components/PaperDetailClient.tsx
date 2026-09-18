"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiRequest, clearToken, getToken, Paper } from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function PaperDetailClient({ paperId }: { paperId: string }) {
  const router = useRouter();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    apiRequest<Paper>(`/papers/${paperId}`, {}, token)
      .then(setPaper)
      .catch((requestError) => {
        if (requestError?.status === 401) {
          clearToken();
          router.replace("/login");
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "无法加载论文");
      });
  }, [paperId, router]);

  if (error) {
    return <main className="center-state"><div><p className="error-message">{error}</p><Link href="/library">返回论文库</Link></div></main>;
  }
  if (!paper) return <main className="center-state">正在加载论文…</main>;

  return (
    <main className="app-shell narrow-shell">
      <header className="app-header">
        <Link href="/library" className="brand">PaperGPT</Link>
        <Link href="/library" className="secondary-button">返回 Library</Link>
      </header>
      <article className="detail-card">
        <span className="status-badge">{paper.parse_status}</span>
        <h1>{paper.title || paper.original_filename}</h1>
        <dl className="detail-list">
          <div><dt>文件名</dt><dd>{paper.original_filename}</dd></div>
          <div><dt>上传时间</dt><dd>{new Date(paper.created_at).toLocaleString("zh-CN")}</dd></div>
          <div><dt>文件大小</dt><dd>{formatBytes(paper.file_size)}</dd></div>
          <div><dt>文档状态</dt><dd>{paper.parse_status}</dd></div>
          <div><dt>Paper ID</dt><dd className="mono">{paper.id}</dd></div>
        </dl>
        <p className="muted detail-note">Phase 1 仅展示基础元数据，PDF Reader 与内容解析尚未实现。</p>
      </article>
    </main>
  );
}
